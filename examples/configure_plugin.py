"""Record this checkout for the installed plugin cache; never commit the result."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'chatgpt-plugin/plugins/garmin-learning/.project-path'
path.write_text(str(root)+'\n', encoding='utf-8')
path.chmod(0o600)
print('Local plugin path configured. Install/reload the plugin from this checkout.')
