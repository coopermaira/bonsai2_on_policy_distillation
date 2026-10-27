import json,unittest
from core import SYSTEM,compact,parse_action
from runtime import action_text
class NativeTests(unittest.TestCase):
 def test_single_native_action(self):
  msg={'tool_calls':[{'id':'t1','function':{'name':'act','arguments':'{"command":"printf hello"}'}}]}
  self.assertEqual(parse_action(action_text(msg)),{'command':'printf hello'})
  for calls in [msg['tool_calls']*2,[{'function':{'name':'wrong','arguments':'{}'}}]]:
   with self.assertRaises(ValueError):action_text({'tool_calls':calls})
 def test_compaction_preserves_call_result_pair(self):
  messages=[{'role':'system','content':SYSTEM},{'role':'user','content':'immutable task'}]
  for i in range(20):
   messages.extend([{'role':'assistant','content':'old material '*1000,'tool_calls':[{'id':str(i),'type':'function','function':{'name':'act','arguments':'{"command":"ls"}'}}]}, {'role':'tool','tool_call_id':str(i),'content':'old observation'}])
  messages.extend([{'role':'assistant','content':'','tool_calls':[{'id':'last','type':'function','function':{'name':'act','arguments':'{"command":"pwd"}'}}]}, {'role':'tool','tool_call_id':'last','content':'LATEST EVIDENCE'}])
  result=compact(messages,'immutable task','NOTE',21,lambda ms:len(json.dumps(ms)),4000)
  self.assertEqual(result[-2]['tool_calls'][0]['id'],result[-1]['tool_call_id'])
  self.assertEqual(result[-1]['content'],'LATEST EVIDENCE')
  self.assertNotEqual(result[2]['role'],'tool')
if __name__=='__main__':unittest.main()
