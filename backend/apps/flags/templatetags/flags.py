from apps.flags.utils import is_flag_active
from django import template

register = template.Library()


class FlagNode(template.Node):
    def __init__(self, flag_name: str, nodelist):
        self.flag_name = flag_name
        self.nodelist = nodelist

    def render(self, context):
        request = context.get("request")
        user = request.user if request else None
        if is_flag_active(self.flag_name, user):
            return self.nodelist.render(context)
        return ""


@register.tag("flag")
def flag_tag(parser, token):
    """
    Conditionally render a block based on a feature flag.

    Usage::

        {% load flags %}
        {% flag "my-feature" %}
            <p>New feature content</p>
        {% endflag %}
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError(f"'{bits[0]}' tag requires exactly one argument")
    flag_name = bits[1].strip("'\"")
    nodelist = parser.parse(("endflag",))
    parser.delete_first_token()
    return FlagNode(flag_name, nodelist)
