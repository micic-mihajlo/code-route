import json
import mimetypes
import os

from .base import BaseTool


class FileContentReaderTool(BaseTool):
    name = "filecontentreadertool"
    description = '''
    Reads content from multiple files and returns their contents.
    Accepts a list of file paths and returns a dictionary with file paths as keys
    and their content as values.
    Handles file reading errors gracefully with built-in Python exceptions.
    When given a directory, recursively reads all text files while skipping binaries and common ignore patterns.
    '''
    
    # Text file extensions that should always be read (not binary)
    TEXT_EXTENSIONS = {
        '.txt', '.md', '.rst', '.markdown',
        # Code files
        '.py', '.js', '.ts', '.tsx', '.jsx', '.mjs', '.cjs',
        '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php',
        '.swift', '.kt', '.kts', '.scala', '.clj', '.ex', '.exs', '.erl', '.hs',
        '.lua', '.r', '.m', '.mm', '.pl', '.pm', '.sh', '.bash', '.zsh', '.fish',
        '.ps1', '.psm1', '.bat', '.cmd', '.awk', '.sed',
        # Config files
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.config',
        '.xml', '.html', '.htm', '.xhtml', '.css', '.scss', '.sass', '.less',
        '.sql', '.graphql', '.proto', '.thrift',
        # Other text
        '.csv', '.tsv', '.env.example', '.gitignore', '.dockerignore',
        '.editorconfig', '.prettierrc', '.eslintrc', '.babelrc',
        'Dockerfile', 'Makefile', 'CMakeLists.txt', 'Cargo.toml', 'go.mod',
    }

    # ignore lists
    IGNORE_PATTERNS = {
        # hidden files and directories
        '.git', '.svn', '.hg', '.DS_Store', '.env', '.idea', '.vscode', '.settings',
        # build directories
        'node_modules', '__pycache__', 'build', 'dist', 'venv', 'env', 'bin', 'obj',
        'target', 'out', 'Debug', 'Release', 'x64', 'x86', 'builds', 'coverage',
        # binary file extensions
        '.pyc', '.pyo', '.so', '.dll', '.dylib', '.pdb', '.ilk', '.exp', '.map',
        '.exe', '.bin', '.dat', '.db', '.sqlite', '.sqlite3', '.o', '.cache',
        '.lib', '.a', '.sys', '.ko', '.obj', '.iso', '.msi', '.msp', '.msm',
        '.img', '.dmg', '.class', '.jar', '.war', '.ear', '.aar', '.apk',
        # media files
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.psd', '.ai', '.eps',
        '.mp3', '.mp4', '.avi', '.mov', '.wav', '.aac', '.m4a', '.wma', '.midi',
        '.flv', '.mkv', '.wmv', '.m4v', '.webm', '.3gp', '.mpg', '.mpeg', '.m2v',
        '.ogg', '.ogv', '.webp', '.heic', '.raw', '.svg', '.ico', '.icns',
        # archive files
        '.zip', '.tar', '.gz', '.rar', '.7z', '.pkg', '.deb', '.rpm', '.snap',
        '.bz2', '.xz', '.cab', '.tgz', '.tbz2', '.lz', '.lzma', '.tlz',
        # ide and editor files
        '.sln', '.suo', '.user', '.workspace', '.project', '.classpath', '.iml',
        # log and temp files
        '.log', '.tmp', '.temp', '.swp', '.bak', '.old', '.orig', '.pid'
    }

    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of file paths to read"
            }
        },
        "required": ["file_paths"]
    }

    def _should_skip(self, path: str) -> bool:
        """Determine if a file or directory should be skipped."""
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()

        # skip if name or extension matches ignore patterns
        if name in self.IGNORE_PATTERNS or ext in self.IGNORE_PATTERNS:
            return True

        # skip hidden files/directories (starting with .) except common config files
        if name.startswith('.') and name not in {'.gitignore', '.env.example', '.editorconfig'}:
            return True

        # if it's a known text extension, don't skip
        if ext in self.TEXT_EXTENSIONS or name in self.TEXT_EXTENSIONS:
            return False

        # if it's a file, check if it's binary using mimetype
        if os.path.isfile(path):
            mime_type, _ = mimetypes.guess_type(path)
            # Only skip if mimetype is known and not text
            if mime_type and not mime_type.startswith('text/') and not mime_type.startswith('application/json'):
                return True

        return False

    def _read_file(self, file_path: str) -> str:
        """Safely read a file and handle errors."""
        try:
            if not os.path.exists(file_path):
                return "Error: File not found"

            if self._should_skip(file_path):
                return "Skipped: Binary or ignored file type"

            with open(file_path, encoding='utf-8') as file:
                return file.read()

        except PermissionError:
            return "Error: Permission denied"
        except IsADirectoryError:
            return "Error: Path is a directory"
        except UnicodeDecodeError:
            return "Error: Unable to decode file (likely binary)"
        except Exception as e:
            return f"Error: {e!s}"

    def _read_directory(self, dir_path: str) -> dict:
        """Recursively read all files in a directory."""
        results = {}

        try:
            for root, dirs, files in os.walk(dir_path):
                # filter out directories to skip
                dirs[:] = [d for d in dirs if not self._should_skip(os.path.join(root, d))]

                # process files
                for file in files:
                    file_path = os.path.join(root, file)
                    if not self._should_skip(file_path):
                        content = self._read_file(file_path)
                        results[file_path] = content

        except Exception as e:
            results[dir_path] = f"Error reading directory: {e!s}"

        return results

    def execute(self, **kwargs) -> str:
        file_paths = kwargs.get('file_paths', [])
        results = {}

        try:
            for path in file_paths:
                if os.path.isdir(path):
                    # if it's a directory, read it recursively
                    dir_results = self._read_directory(path)
                    results.update(dir_results)
                else:
                    # if it's a file, read it directly
                    content = self._read_file(path)
                    results[path] = content

            return json.dumps(results, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)