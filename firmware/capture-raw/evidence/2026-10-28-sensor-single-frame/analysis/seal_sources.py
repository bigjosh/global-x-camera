"""List reproducible offline analysis dependencies; no instrument imports."""
from pathlib import Path
import json
from analyze_promotion import HERE,PREVIOUS,prior,sha
paths=[Path(__file__),HERE/'analyze_promotion.py',HERE/'analyze_flash_awake.py',HERE/'render_promotion.py',
       PREVIOUS,prior.SOURCE,
       prior.normal.DEPS/'analyze_warm_ablations.py',prior.normal.DEPS/'analyze_existing_baseline.py']
out={str(p.resolve()):sha(p) for p in paths}
(HERE/'analysis-sources.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
