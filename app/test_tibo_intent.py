import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.tibo_intent import LANGUAGES, validate_intent, publish_intent, load_intent

NOW = datetime.now(timezone.utc)
STAMP = (NOW - timedelta(minutes=1)).isoformat()
POST = {"id":"123", "created_at":STAMP, "text":"Resets all propagated. That will be all.", "url":"https://x.com/thsottiaux/status/123"}
SNAPSHOT = {"health":"ok", "fetched_at":STAMP, "posts":[POST]}

def candidate():
    return {"schema_version":1,"scope":"public_posts_not_private_intent","source_fetched_at":STAMP,"generated_at":STAMP,"outlook":"reset_reported","confidence":"high","locales":{lang:dict(summary="Interpretation",rationale="Evidence",counter_evidence="No next-reset promise",watch_next="Watch later statements") for lang in LANGUAGES},"evidence":[{"post_id":"123","quote":"Resets all propagated.","intent":"completion","strength":"direct","locales":{lang:dict(reading="Reported completion",reset_relevance="Not a future reset promise") for lang in LANGUAGES}}]}

class IntentTests(unittest.TestCase):
    def test_valid_analysis_is_projected_and_published(self):
        data=candidate();data['private_debug']='must not leak'
        valid=validate_intent(data,SNAPSHOT,NOW)
        self.assertNotIn('private_debug',valid)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'status.json').write_text(json.dumps(SNAPSHOT));(root/'candidate.json').write_text(json.dumps(data))
            publish_intent(root/'candidate.json',root/'status.json',root/'intent.json')
            self.assertEqual(load_intent(root/'intent.json',SNAPSHOT)['outlook'],'reset_reported')
    def test_fabricated_quote_or_unknown_post_is_rejected(self):
        for field,value in [('quote','He promised tomorrow'),('post_id','999')]:
            data=candidate();data['evidence'][0][field]=value
            self.assertIsNone(validate_intent(data,SNAPSHOT,NOW))
    def test_stale_future_failed_or_replaced_source_is_rejected(self):
        for delta in [timedelta(days=-2),timedelta(days=1)]:
            data=candidate();data['generated_at']=(NOW+delta).isoformat()
            self.assertIsNone(validate_intent(data,SNAPSHOT,NOW))
        for changes in [{'health':'error'},{'fetched_at':NOW.isoformat()}]:
            self.assertIsNone(validate_intent(candidate(),{**SNAPSHOT,**changes},NOW))
    def test_missing_latest_or_language_is_rejected(self):
        snapshot=copy.deepcopy(SNAPSHOT);snapshot['posts'].append({**POST,'id':'456','created_at':NOW.isoformat()})
        self.assertIsNone(validate_intent(candidate(),snapshot,NOW))
        data=candidate();del data['locales']['ko']
        self.assertIsNone(validate_intent(data,SNAPSHOT,NOW))
    def test_wrong_types_and_empty_evidence_fail_closed(self):
        for edits in [{'evidence':[]},{'evidence':[None]},{'confidence':[]},{'locales':None}]:
            self.assertIsNone(validate_intent({**candidate(),**edits},SNAPSHOT,NOW))

if __name__=='__main__': unittest.main()
