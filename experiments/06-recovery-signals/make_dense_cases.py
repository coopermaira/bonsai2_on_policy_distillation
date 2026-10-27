import hashlib
import json
import math
from study import WORK, URLS, http, save
from signals import context, select_turn

metadata=[]
with (WORK/'dense-cases.tokens').open('w') as output:
    for state in ['music_evidence','session_final_review','session_final_reproducer']:
        for model in ['bonsai','fp16']:
            path=WORK/'rollouts'/f'{state}-{model}-00.json'
            if not path.exists():
                continue
            record=json.loads(path.read_text())
            index=select_turn(record)
            turn=record['turns'][index]
            messages=context(record,index)
            rendered=http(URLS['fp16']+'/apply-template',{'messages':messages})['prompt']
            assert rendered==http(URLS['bonsai']+'/apply-template',{'messages':messages})['prompt']
            message=turn['response']['choices'][0]['message']
            content=message.get('content') or ''
            marker='"keystrokes": "'
            at=content.find(marker)
            if at < 0:
                metadata.append({'rollout_id':record['id'],'skipped':'no literal command boundary'})
                continue
            assert rendered.rstrip().endswith('<think>')
            lead=rendered+(message.get('reasoning_content') or '')+'</think>\n\n'
            short=lead+content[:at+len(marker)]
            complete=lead+content
            def tokens(url,text):
                return http(url+'/tokenize',{'content':text,'add_special':True,'parse_special':True})['tokens']
            prefix=tokens(URLS['fp16'],short)
            full=tokens(URLS['fp16'],complete)
            assert full==tokens(URLS['bonsai'],complete)
            common=0
            for a,b in zip(prefix,full):
                if a!=b:break
                common+=1
            assert common >= len(prefix)-8, 'Unexpected token boundary mismatch'
            target=full[common:common+64]
            if not target or common+len(target)>49152:
                metadata.append({'rollout_id':record['id'],'skipped':'context or target length'})
                continue
            ident=hashlib.sha256(record['id'].encode()).hexdigest()[:12]
            output.write(f'{ident} {common} {len(target)}\n')
            output.write(' '.join(map(str,full[:common]))+'\n')
            output.write(' '.join(map(str,target))+'\n')
            metadata.append({'id':ident,'rollout_id':record['id'],'turn':index,'prefix_tokens':common,
                             'target_tokens':len(target),'boundary_backoff_tokens':len(prefix)-common,
                             'full_text_sha256':hashlib.sha256(complete.encode()).hexdigest()})
            # Independent HTTP/native parity check at the first scored position.
            parity = {}
            for name, url in URLS.items():
                result = http(url+'/completion', dict(prompt=full[:common], n_predict=1,
                              temperature=0, n_probs=300000, post_sampling_probs=False,
                              return_tokens=True, cache_prompt=False, seed=1))
                rows = result['completion_probabilities'][0]['top_logprobs']
                assert len(rows) > 100000
                mass = sum(math.exp(row['logprob']) for row in rows)
                assert abs(mass-1) < .002
                parity[name] = {'actual_token_logprob': next(row['logprob'] for row in rows if row['id']==target[0])-math.log(mass),
                                'top1': max(rows,key=lambda row:row['logprob'])['id'], 'vocab_size':len(rows)}
            save(WORK/f'dense-parity-{ident}.json', {'id':ident,'token':target[0],'models':parity})
save(WORK/'dense-cases.json',metadata)
print(json.dumps(metadata),flush=True)
