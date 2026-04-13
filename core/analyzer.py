"""
core/analyzer.py — 프로젝트 파일 구조 분석
"""

import re
from pathlib import Path
from dataclasses import dataclass, field

# 분석 대상 확장자
TARGET_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".kt", ".go", ".rs", ".cpp", ".c", ".h",
    ".rb", ".php", ".swift", ".cs",
}

# 무시할 디렉토리
IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    # IDE 설정 폴더
    ".idea", ".vscode", ".eclipse", ".settings",
    # Android/Gradle 빌드 산출물
    ".gradle", ".kotlin", "build", "generated",
}

# 설정 파일 (구조 이해에 중요)
CONFIG_FILES = {
    "package.json", "pyproject.toml", "setup.py", "requirements.txt",
    "Dockerfile", "docker-compose.yml", ".env.example", "README.md",
    "Makefile", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
}

# 디렉토리 축약 시 "직접 파일 존재"로 간주하지 않을 빌드/설정 파일
_COLLAPSE_IGNORE_FILES = {
    "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
    "proguard-rules.pro", "consumer-rules.pro", "gradle.properties",
    ".gitignore", ".gitattributes", "README.md", "LICENSE",
    "CMakeLists.txt", "Makefile", "Dockerfile",
}

# 프로젝트 진입점으로 간주할 파일명
ENTRY_POINTS = {
    "main.py", "app.py", "run.py", "manage.py", "__main__.py",
    "server.py", "wsgi.py", "asgi.py", "cli.py",
    "index.js", "index.ts", "app.js", "app.ts", "server.js", "server.ts",
}

# Python import 구문 추출 정규식
_PY_IMPORT_RE = re.compile(
    r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)

# 디렉토리 이름 → 역할 설명
DIR_DESCRIPTIONS = {
    "src": "핵심 소스 코드",
    "tests": "테스트 스위트",
    "test": "테스트 스위트",
    "docs": "사용자 문서",
    "doc": "사용자 문서",
    "examples": "예제 프로젝트",
    "example": "예제 프로젝트",
    ".github": "CI/CD 및 이슈 템플릿",
    ".devcontainer": "개발 환경 설정",
    "scripts": "빌드/배포 스크립트",
    "config": "설정 파일",
    "api": "API 레이어",
    "core": "핵심 비즈니스 로직",
    "utils": "유틸리티",
    "lib": "라이브러리",
    "components": "UI 컴포넌트",
    "models": "데이터 모델",
    "views": "뷰 레이어",
    "controllers": "컨트롤러",
    "services": "서비스 레이어",
    "migrations": "DB 마이그레이션",
    "static": "정적 파일",
    "templates": "HTML 템플릿",
    "assets": "정적 자산",
    "agent": "AI 에이전트 로직",
    "cli": "CLI 인터페이스",
    "cmd": "커맨드 모듈",
}


@dataclass
class FileInfo:
    path: Path
    relative_path: str
    extension: str
    size_bytes: int
    is_config: bool = False
    is_entry_point: bool = False  # main.py, app.py 등 진입점 여부
    import_count: int = 0         # 다른 파일이 이 파일을 import한 횟수


@dataclass
class DirSummary:
    display_path: str   # e.g. "src/click/" or "tests/"
    file_count: int
    description: str


@dataclass
class ProjectStructure:
    root: Path
    repo_name: str
    all_files: list[FileInfo] = field(default_factory=list)
    code_files: list[FileInfo] = field(default_factory=list)
    config_files: list[FileInfo] = field(default_factory=list)
    language_stats: dict[str, int] = field(default_factory=dict)
    dir_summaries: list[DirSummary] = field(default_factory=list)


class ProjectAnalyzer:
    def analyze(self, repo_path: Path) -> ProjectStructure:
        structure = ProjectStructure(
            root=repo_path,
            repo_name=repo_path.name,
        )
        self._walk(repo_path, structure)
        self._analyze_imports(structure)
        structure.dir_summaries = self._build_dir_summaries(repo_path)
        return structure

    def _walk(self, root: Path, structure: ProjectStructure) -> None:
        for item in root.rglob("*"):
            if any(part in IGNORE_DIRS for part in item.parts):
                continue
            if not item.is_file():
                continue

            rel = str(item.relative_to(root))
            ext = item.suffix.lower()
            size = item.stat().st_size
            is_config = item.name in CONFIG_FILES

            info = FileInfo(
                path=item,
                relative_path=rel,
                extension=ext,
                size_bytes=size,
                is_config=is_config,
                is_entry_point=item.name in ENTRY_POINTS,
            )
            structure.all_files.append(info)

            if is_config:
                structure.config_files.append(info)
            elif ext in TARGET_EXTENSIONS:
                structure.code_files.append(info)
                structure.language_stats[ext] = (
                    structure.language_stats.get(ext, 0) + 1
                )

    def _analyze_imports(self, structure: ProjectStructure) -> None:
        """
        각 코드 파일의 import 구문을 파싱하여 프로젝트 내 파일의 import_count를 집계합니다.
        많이 import될수록 해당 파일이 프로젝트에서 중요한 역할을 한다고 판단합니다.
        현재 Python 파일을 지원합니다.
        """
        # 빠른 조회를 위해 상대 경로 → FileInfo 맵 구성
        path_map: dict[str, FileInfo] = {
            f.relative_path.replace("\\", "/"): f
            for f in structure.code_files
        }

        for file_info in structure.code_files:
            if file_info.extension != ".py":
                continue
            try:
                source = file_info.path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for match in _PY_IMPORT_RE.finditer(source):
                module = match.group(1) or match.group(2)
                if not module:
                    continue
                # "core.analyzer" → "core/analyzer.py" 형태로 변환하여 조회
                candidate = module.replace(".", "/") + ".py"
                if candidate in path_map:
                    path_map[candidate].import_count += 1

    def _build_dir_summaries(self, root: Path) -> list[DirSummary]:
        top_dirs = sorted(
            [p for p in root.iterdir() if p.is_dir() and p.name not in IGNORE_DIRS],
            key=lambda p: p.name.lstrip("."),
        )
        summaries: list[DirSummary] = []
        for d in top_dirs:
            self._expand_dir(d, root, summaries, prefix="", depth=0)
        return summaries

    def _expand_dir(
        self, d: Path, root: Path, summaries: list, prefix: str, depth: int
    ) -> None:
        """체인 축약 후 하위 디렉토리가 여럿이면 재귀적으로 펼쳐서 summaries에 추가."""
        collapsed_suffix, actual_path = self._collapse_chain(d)
        full_prefix = prefix + collapsed_suffix

        try:
            subdirs = sorted(
                [p for p in actual_path.iterdir()
                 if p.is_dir() and p.name not in IGNORE_DIRS],
                key=lambda p: p.name,
            )
        except PermissionError:
            subdirs = []

        # 하위 디렉토리가 여럿이고 아직 펼칠 여유가 있으면 재귀
        if len(subdirs) >= 2 and depth < 2:
            for sub in subdirs:
                self._expand_dir(sub, root, summaries, prefix=full_prefix, depth=depth + 1)
        else:
            file_count = self._count_files(actual_path, root)
            if file_count == 0:
                return
            description = DIR_DESCRIPTIONS.get(
                actual_path.name.lower(), f"{actual_path.name} 관련 파일"
            )
            summaries.append(DirSummary(
                display_path=full_prefix,
                file_count=file_count,
                description=description,
            ))

    def _collapse_chain(self, d: Path) -> tuple[str, Path]:
        """단일 자식 디렉토리 체인을 끝까지 내려가 (표시 경로, 실제 경로) 반환.
        빌드/설정 파일(_COLLAPSE_IGNORE_FILES)은 직접 파일로 취급하지 않는다."""
        parts = [d.name]
        current = d
        while True:
            try:
                subdirs = [p for p in current.iterdir()
                           if p.is_dir() and p.name not in IGNORE_DIRS]
                real_files = [p for p in current.iterdir()
                              if p.is_file() and p.name not in _COLLAPSE_IGNORE_FILES]
            except PermissionError:
                break
            if len(subdirs) == 1 and not real_files:
                current = subdirs[0]
                parts.append(current.name)
            else:
                break
        return "/".join(parts) + "/", current

    def _count_files(self, path: Path, root: Path) -> int:
        return sum(
            1 for f in path.rglob("*")
            if f.is_file()
            and not any(part in IGNORE_DIRS for part in f.relative_to(root).parts)
        )
