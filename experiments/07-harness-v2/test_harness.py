import copy,json,tempfile,unittest
from pathlib import Path
from core import DEFAULT,SYSTEM,InfrastructureError,atomic,compact,parse_action,prepare_messages,recall,score_groups,task_instruction

class CoreTests(unittest.TestCase):
    def test_deadline_removal_preserves_task_contract(self):
        self.assertEqual(task_instruction('Produce 5s notifications. You have 28800 seconds to complete this task. Do not cheat.'),'Produce 5s notifications. Do not cheat.')
    def test_truncated_or_ambiguous_commands_not_salvaged(self):
        for text in ['{"command":"rm','{"command":"echo x","done":true}','{"wait":false}','{"recall":{"turn":-1}}']:
            with self.assertRaises((ValueError,TypeError)):parse_action(text)
    def test_fenced_json_and_memory(self):
        self.assertEqual(parse_action('```json\n{"command":"echo ok","memory":"fact"}\n```')['memory'],'fact')
        with self.assertRaises(ValueError):parse_action(json.dumps({'done':True,'memory':'x'*8193}))
    def test_compaction_keeps_task_notebook_latest_and_recall(self):
        messages=[dict(role='system',content=SYSTEM),dict(role='user',content='IMMUTABLE TASK')]
        messages += [dict(role='assistant',content='x'*5000),dict(role='user',content='y'*5000)]*10
        messages += [dict(role='assistant',content='last action'),dict(role='user',content='LATEST EVIDENCE')]
        result=compact(messages,'IMMUTABLE TASK','VERIFIED NOTE',21,lambda ms:len(json.dumps(ms)),4000)
        text=json.dumps(result)
        for fact in ['IMMUTABLE TASK','VERIFIED NOTE','LATEST EVIDENCE','recall']:self.assertIn(fact,text)
        self.assertLessEqual(len(text),4000)
    def test_unfittable_immutable_input_is_infrastructure(self):
        with self.assertRaises(InfrastructureError):compact([{},{}],'x'*10000,'',0,lambda ms:len(json.dumps(ms)),100)
    def test_full_output_reserve_including_last_observation(self):
        c=dict(DEFAULT,context_tokens=10000,output_tokens=3000,output_reserve=500,total_generated_tokens=10000)
        state=dict(turn=1,generated_tokens=100,instruction='task',memory='note',messages=[dict(role='system',content=SYSTEM),dict(role='user',content='task'),dict(role='assistant',content='x'*9000),dict(role='user',content='latest')])
        result,event=prepare_messages(state,c,lambda ms:len(json.dumps(ms)))
        self.assertIsNotNone(event);self.assertLessEqual(len(json.dumps(result)),6500)
    def test_recall_pagination_and_privilege_separation(self):
        with tempfile.TemporaryDirectory() as d:
            atomic(Path(d)/'0001.json',dict(turn=1,assistant={'content':'EARLY FACT'},observation='evidence',private_reference='NEVER EXPOSE'))
            r=recall(d,dict(turn=1,offset=0,limit=18000))
            self.assertIn('EARLY FACT',r['text']);self.assertNotIn('NEVER EXPOSE',r['text'])
            self.assertIn('error',recall(d,dict(turn=2)))
    def test_partial_groups_unknowns_and_parameter_weighting(self):
        t=[dict(name='a[1]',status='passed'),dict(name='a[2]',status='failed'),dict(name='b',status='passed'),dict(name='c',status='failed',message='TimeoutExpired')]
        result=score_groups(t,{'one':['a['],'two':['b'],'unknown':['c']})
        self.assertEqual(result['lower'],50);self.assertAlmostEqual(result['upper'],100*2.5/3)
    def test_fixture_self_test_excluded(self):
        score=score_groups([dict(name='fixture',status='passed')],{'function':['function']},['fixture'])
        self.assertEqual((score['lower'],score['upper']),(0,100))
    def test_native_envelope_complete_action_only(self):
        self.assertEqual(parse_action('<tool_call>\n{"command":"ls /app"}\n</parameter>\n</function>\n</tool_call>'),{'command':'ls /app'})
        for bad in ['<tool_call>{"command":"ls', '<tool_call>{"command":"ls"}</tool_call> trailing', '<tool_call>{"command":"ls"}{"done":true}</tool_call>', '<tool_call>{"command":"ls\n</parameter></tool_call>']:
            with self.assertRaises(ValueError):parse_action(bad)
    def test_atomic_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';atomic(p,{'turn':1});atomic(p,{'turn':2})
            self.assertEqual(json.loads(p.read_text()),{'turn':2})
            self.assertFalse(p.with_name('state.json.tmp').exists())

if __name__=='__main__':unittest.main(verbosity=2)
