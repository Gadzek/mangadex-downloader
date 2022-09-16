from .utils import (
    Paginator, 
    dynamic_bars, 
    IteratorEmpty, 
    get_key_value, 
    split_comma_separated
)
from ..iterator import (
    IteratorManga,
    IteratorUserLibraryFollowsList,
    IteratorUserLibraryList,
    IteratorUserLibraryManga,
    IteratorUserList,
    iter_random_manga
)
from ..utils import input_handle, validate_url
from ..errors import InvalidURL, MangaDexException, PillowNotInstalled
from ..network import Net
from ..manga import ContentRating
from ..group import Group

def preview_cover_manga(manga):
    try:
        from PIL import Image
    except ImportError:
        raise PillowNotInstalled("Pillow is not installed") from None

    r = Net.mangadex.get(manga.cover_art, stream=True)
    im = Image.open(r.raw)

    print("\nCLOSE THE IMAGE PREVIEW TO CONTINUE\n")

    im.show(manga.title)
    im.close()

def preview_list(mdlist):
    text_init = f'List of mangas from MangaDex list \"{mdlist.name}\"'

    print('\n')
    print(text_init)
    print(dynamic_bars(text_init))
    for manga in mdlist.iter_manga():
        print(manga.title)
    print('\n\n')

class BaseCommand:
    """A base class that will handle command prompt"""
    def __init__(self, parser, args, iterator, text, limit=10):
        self.args_parser = parser
        self.args = args
        self.text = text
        self.paginator = Paginator(iterator, limit)
        self._text_choices = ""

    def _error(self, message, exit=False):
        """Function to print error, yes"""
        msg = f'\nError: {message}\n'
        if exit:
            self.args_parser.error(message)
        else:
            print(msg)

    def _insert_choices(self, choices, action='next'):
        text = ""
        func = getattr(self.paginator, action)

        for pos, item in func():
            choices[str(pos)] = item
            text += f"({pos}). {item}\n" 

        self._text_choices = text

    def _print_choices(self):
        header = dynamic_bars(self.text) + "\n"

        final_text = ""
        # Title with bars header
        final_text += header
        final_text += self.text + "\n"
        final_text += header

        # Choices
        final_text += self._text_choices

        # Empty line for separator
        final_text += "\n"

        # Prompt instruction
        final_text += 'type "next" to show next results\n'
        final_text += 'type "previous" to show previous results'
        if self.preview():
            final_text += '\ntype "preview NUMBER" to show more details about selected result. ' \
                          'For example: "preview 2"'
        
        print(final_text)

    def preview(self):
        """Check if this command support preview.
        
        Must return ``True`` or ``False``.
        """
        return False

    def on_empty_error(self):
        """This function will be called if :attr:`BaseCommand.iterator` 
        returns nothing on first prompt.
        """
        pass

    def on_preview(self, item):
        """This function is called when command ``preview`` is selected.
        
        :func:`BaseCommand.preview()` must return ``True`` in order to get this called.
        """
        pass

    def _return_from(self, pos):
        choices = {}

        try:
            self._insert_choices(choices)
        except IteratorEmpty:
            self.on_empty_error()
            return None

        while True:

            try:
                result = choices[pos]
            except KeyError:
                result = None
            
            if result is not None:
                yield result
                break
            elif pos == "*":
                for item in choices.values():
                    yield item

            try:
                self._insert_choices(choices)
            except IteratorEmpty:
                self._error("There are no more results", exit=True)
            except IndexError:
                self._error("Choices are out of range, try again")

    def prompt(self, input_pos=None):
        """Begin ask question to user"""
        choices = {}

        if input_pos:
            return self._return_from(input_pos)

        # Begin inserting choices for question
        try:
            self._insert_choices(choices)
        except IteratorEmpty:
            self.on_empty_error()
            return

        answer = None
        while True:
            if answer is not None:
                if answer.startswith('preview') and self.preview():
                    answer_item = answer.split('preview', maxsplit=1)[1].strip()
                    try:
                        item = choices[answer_item]
                    except KeyError:
                        self._error("Invalid choice, try again")
                    else:
                        self.on_preview(item)

                    answer = None
                    continue

                elif answer.startswith("next"):
                    action = "next"
                elif answer.startswith("previous"):
                    action = "previous"
                else:
                    try:
                        item = choices[answer]
                    except KeyError:
                        self._error("Invalid choice, try again")
                        answer = None
                    else:
                        return item
                
                try:
                    self._insert_choices(choices, action)
                except IteratorEmpty:
                    self._error("There are no more results")
                except IndexError:
                    self._error("Choices are out of range, try again")
        
            self._print_choices()
            answer = input_handle("=> ")

class MangaDexCommand(BaseCommand):
    """Command specialized for MangaDex"""
    def prompt(self, *args, **kwargs):
        answer = super().prompt(*args, **kwargs)
        ids = []

        # Make sure results are never duplicated
        def iter_answer():
            for item in answer:
                if item.id not in ids:
                    ids.append(item.id)
                    yield item.id
                else:
                    continue

        # "input_pos" argument from prompt() is used
        try:
            iter(answer)
        except TypeError:
            return [answer.id]
        else:
            return iter_answer()

                

class MangaCommand(MangaDexCommand):
    """Command specialized for manga related"""
    def preview(self):
        return True

    def on_preview(self, item):
        preview_cover_manga(item)

class MDListCommand(MangaDexCommand):
    """Command specialized for MangaDex list related"""
    def preview(self):
        return True

    def on_preview(self, item):
        preview_list(item)

class MangaLibraryCommand(MangaCommand):
    """A command that will prompt user to select which manga want to download from user library"""

    def __init__(self, parser, args, input_text):
        _, status = get_key_value(input_text, sep=':')

        if not status:
            # To prevent error "invalid value"
            status = None

        user = Net.mangadex.user

        super().__init__(
            parser,
            args,
            IteratorUserLibraryManga(status),
            f'List of manga from user library "{user.name}"'
        )

        self.user = user

    def on_empty_error(self):
        self.args_parser.error(f'User "{self.user.name}"')

class ListLibraryCommand(MDListCommand):
    """A command that will prompt user to select which list want to download from user library"""
    def __init__(self, parser, args, input_text):
        _, user = get_key_value(input_text, sep=':')

        user_id = None
        if user:
            try:
                user_id = validate_url(user)
            except InvalidURL as e:
                parser.error(f'"{user}" is not a valid user')
        
        if user:
            iterator = IteratorUserList(user_id)
        else:
            iterator = IteratorUserLibraryList()
        
        try:
            user = iterator.user
        except AttributeError:
            # Logged in user
            user = Net.mangadex.user

        super().__init__(
            parser,
            args,
            iterator,
            f'List of saved MDList from user "{user.name}"'
        )

        self.user = user
    
    def on_empty_error(self):
        self.args_parser.error(f'User "{self.user.name} has no saved lists"')

class FollowedListLibraryCommand(MDListCommand):
    """A command that will prompt user to select which list want to download from followed lists user """

    def __init__(self, parser, args, input_text):
        iterator = IteratorUserLibraryFollowsList()

        user = Net.mangadex.user

        super().__init__(
            parser,
            args,
            iterator,
            f'List of followed MDlist from user "{user.name}"'
        )

        self.user = user
    
    def on_empty_error(self):
        self.args_parser.error(f'User "{self.user.name}" has no followed lists')

class SearchMangaCommand(MangaCommand):
    """A command that will prompt user to select which manga to download (from search)"""
    def __init__(self, parser, args, input_text):
        # Parse filters
        orders = {}
        filter_kwargs = {}
        filters = args.search_filter or []
        for f in filters:
            key, value  = get_key_value(f)
            try:
                value_filter_kwargs = filter_kwargs[key]
            except KeyError:
                filter_kwargs[key] = split_comma_separated(value)
            else:
                # Found duplicate filter with different value
                if isinstance(value_filter_kwargs, str):
                    new_values = [value_filter_kwargs]
                else:
                    new_values = value_filter_kwargs

                values = split_comma_separated(value, single_value_to_list=True)
                new_values.extend(values)

                filter_kwargs[key] = new_values

        # We cannot put "order[key]" into function parameters
        # that would cause syntax error
        for key in filter_kwargs.keys():
            if 'order' in key:
                orders[key] = filter_kwargs[key]

        # Remove "order[key]" from filter_kwargs
        # to avoid syntax error
        for key in orders.keys():
            filter_kwargs.pop(key)

        # This much safer
        filter_kwargs['order'] = orders

        iterator = IteratorManga(input_text, **filter_kwargs)
        super().__init__(
            parser,
            args,
            iterator,
            f'Manga search results for "{input_text}"'
        )
        
        self.input_text = input_text
    
    def on_empty_error(self):
        self.args_parser.error(f'Manga search results for "{self.input_text}" are empty')

class GroupMangaCommand(MangaCommand):
    """A command that will prompt user to select which manga to download (from scanlator group)"""
    def __init__(self, parser, args, input_text):
        # Getting group id
        _, group_id = get_key_value(input_text, sep=':')
        if not group_id:
            parser.error("group id or url are required")
        
        group_id = validate_url(group_id)
        group = Group(group_id)

        iterator = IteratorManga(None, group=group.id)
        text = f'List of manga from group "{group.name}"'

        super().__init__(
            parser,
            args,
            iterator,
            text
        )
        
        self.group = group

    def on_empty_error(self):
        self.args_parser.error(f'Group "{self.group.name}" has no uploaded mangas')

class RandomMangaCommand(MangaCommand):
    def __init__(self, parser, args, input_text):
        # Parse content ratings
        _, raw_cr = get_key_value(input_text, sep=':')
        content_ratings = split_comma_separated(raw_cr, single_value_to_list=True)

        if not content_ratings[0]:
            # Fallback to default value
            content_ratings = [i.value for i in ContentRating]
        else:
            # Verify it
            try:
                content_ratings = [ContentRating(i).value for i in content_ratings]
            except ValueError as e:
                raise MangaDexException(e)

        iterator = iter_random_manga(content_ratings)
        text = f'Found random manga'
        super().__init__(
            parser,
            args,
            iterator,
            text,
            limit=5
        )
    
    def on_empty_error(self):
        # This should never happened
        self.args_parser.error('Unknown error when fetching random manga')

registered_commands = {
    "search": SearchMangaCommand,
    "fetch_library_manga": MangaLibraryCommand,
    "fetch_library_list": ListLibraryCommand,
    "fetch_library_follows_list": FollowedListLibraryCommand,
    "random": RandomMangaCommand,
    "fetch_group": GroupMangaCommand
}