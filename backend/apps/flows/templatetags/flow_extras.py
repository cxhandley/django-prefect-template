from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Access a dictionary value by key in templates: {{ dict|get_item:key }}"""
    return dictionary.get(key)
