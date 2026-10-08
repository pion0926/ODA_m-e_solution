"""Interpret explicit yes/no indicators without inventing a numeric rate."""
import re


def apply_categorical_status(item):
    item.pop('achievement_label', None)
    if not re.search(r'\(\s*유\s*/\s*무\s*\)', str(item.get('indicator') or '')):
        return
    if item.get('measurement_status') in {'incomplete','conflict','no_measurement'}:
        return
    target,actual=item.get('target'),item.get('actual')
    if target not in {'유','무'} or actual not in {'유','무'}:
        return
    item['achievement_rate']=None
    item['status']='ok' if actual==target else 'under'
    item['achievement_label']='충족' if actual==target else '미충족'
