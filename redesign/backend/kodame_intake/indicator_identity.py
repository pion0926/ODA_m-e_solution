"""Source-independent identity; ambiguous matches receive new identities."""
import re
import uuid
from collections import Counter


def concept(text):
    # Only an exactly unchanged semantic label carries identity automatically.
    # A changed target/label is deliberately left as a new identity for review.
    return re.sub(r'\s+', '', str(text)).casefold()


def assign_identities(model, previous, project_id, source_id):
    prior = [(t['id'], i) for t in (previous or {}).get('tiers', []) for i in t['indicators']]
    count = Counter((tier, concept(i['text'])) for tier, i in prior)
    lookup = {(tier, concept(i['text'])): i for tier, i in prior}
    for tier in model['tiers']:
        for item in tier['indicators']:
            key = (tier['id'], concept(item['text']))
            old = lookup.get(key) if count[key] == 1 else None
            item['stable_id'] = (old or {}).get('stable_id') or str(uuid.uuid5(uuid.NAMESPACE_URL,
                f'kodame:{project_id}:{source_id}:{tier["id"]}:{item["id"]}:{key[1]}'))
            item['source_version_id'] = str(source_id)
            item['previous_indicator_id'] = old.get('id') if old else None
