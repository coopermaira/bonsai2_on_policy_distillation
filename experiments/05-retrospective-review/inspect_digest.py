"""Read-only inspection view: remove embedded command JSON from message prose."""
import json,sys
from pathlib import Path
root=Path('/home/cm/bonsai-retrospective')
ident=sys.argv[1];lo=int(sys.argv[2]);hi=int(sys.argv[3])
for n in range(lo,hi+1):
 p=root/'review'/ident/f'{n:03}.txt'
 if not p.exists():continue
 text=p.read_text().split('\n\nCOMMANDS\n')[0]
 for i,c in enumerate(text):
  if c!='{':continue
  try:
   obj,end=json.JSONDecoder().raw_decode(text[i:])
   if isinstance(obj,dict) and 'commands' in obj:
    text=text[:i]+'\nAnalysis: '+str(obj.get('analysis',''))+'\nPlan: '+str(obj.get('plan',''));break
  except ValueError:pass
 # Invalid JSON can contain huge keystrokes strings; retain the preceding prose.
 if '"commands"' in text:text=text[:text.find('"commands"')]
 print(text+'\n')
