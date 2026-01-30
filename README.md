# md2hwpx

**md2hwpx**는 마크다운(`.md`)을 아래아 한글 HWPX(`.hwpx`)로 변환해주는 파이썬 도구입니다. Pandoc 없이 순수 파이썬으로 동작합니다.

[pypandoc-hwpx 포크](https://github.com/msjang/pypandoc-hwpx)이며, 새로운 기능과 개선을 계속 추가하고 있습니다.

[English README](https://github.com/msjang/md2hwpx/blob/main/README.en.md)

## 주요 기능

- **Pandoc 없이 변환**: Marko 파서 + XML 생성으로 순수 파이썬 변환
- **CLI 및 Python API** 제공
- **YAML 프론트매터** 지원: 문서 `title` 메타데이터 작성
- **템플릿 기반 스타일**: 제목/본문/리스트/표 셀 플레이스홀더로 WYSIWYG 스타일링
- **표 지원**: GFM 표, 정렬 및 컬럼 비율 반영
- **리스트**: 중첩 목록과 시작 번호 지원
- **이미지 임베딩**: 로컬 이미지 삽입, 크기 보정, 경로 검증
- **인용문, 수평선**
- **각주**
- **확장 헤더**: 1–9 레벨
- **디버그 출력**: `.json` AST, `.html` 출력

## 요구 사항

- **Python 3.9+**
- **라이브러리**: marko, python-frontmatter, Pillow

## 설치

### PyPI 설치 (권장)

```bash
pip install md2hwpx
```

### 소스 설치

```bash
git clone https://github.com/msjang/md2hwpx.git
cd md2hwpx
pip install -e .
```

## 사용 방법

### CLI

```bash
# Markdown -> HWPX
md2hwpx input.md -o output.hwpx

# 참조 템플릿 지정
md2hwpx input.md --reference-doc=custom.hwpx -o output.hwpx

# 디버그: JSON AST 출력
md2hwpx input.md -o debug.json

# 디버그: HTML 출력
md2hwpx input.md -o output.html
```

### CLI 옵션

| 옵션 | 설명 |
|------|------|
| `input_file` | 입력 마크다운 파일 (.md, .markdown) |
| `-o`, `--output` | 출력 파일 (.hwpx, .json, .html) |
| `-r`, `--reference-doc` | 스타일/페이지 설정용 참조 HWPX (기본: 내장 blank.hwpx) |
| `--verbose` | 디버그 로그 출력 |
| `-q`, `--quiet` | 오류 외 출력 억제 |
| `-v`, `--version` | 버전 출력 |

### 프론트매터 (title)

```markdown
---
title: 문서 제목
---

# 제목
```

`title` 값은 HWPX 문서 메타데이터에 기록됩니다.

### Python API

```python
from md2hwpx import MarkdownToHwpx, MarkoToPandocAdapter

adapter = MarkoToPandocAdapter()
ast = adapter.parse("# Hello World\n\nThis is a paragraph.")

MarkdownToHwpx.convert_to_hwpx(
    input_path="input.md",
    output_path="output.hwpx",
    reference_path="blank.hwpx",
    json_ast=ast,
)
```

## 스타일 커스터마이징 (템플릿)

한컴오피스에서 참조 HWPX 템플릿을 편집하면 출력 스타일을 손쉽게 제어할 수 있습니다.

### 방법 1: 플레이스홀더 방식 (권장)

템플릿에 플레이스홀더 텍스트를 넣고 원하는 서식을 적용합니다.

| 플레이스홀더 | 마크다운 요소 |
|-------------|---------------|
| `{{H1}}` | `# 제목 1` |
| `{{H2}}` | `## 제목 2` |
| `{{H3}}` | `### 제목 3` |
| `{{H4}}`–`{{H9}}` | `####`–`#########` |
| `{{BODY}}` | 본문 |

#### 리스트 플레이스홀더

리스트 레벨(1–7)별 스타일을 정의할 수 있습니다.

- `{{LIST_BULLET_1}}` … `{{LIST_BULLET_7}}`
- `{{LIST_ORDERED_1}}` … `{{LIST_ORDERED_7}}`

플레이스홀더 앞 텍스트는 접두(prefix)로 사용됩니다(예: `1. `, `가. `).
템플릿 단락에 번호 매기기를 지정하면 해당 번호 스타일을 유지합니다.

#### 표 셀 플레이스홀더

표 셀 스타일을 세부적으로 지정하려면 아래 12개 플레이스홀더를 사용하세요.

- `{{CELL_HEADER_LEFT}}`, `{{CELL_HEADER_CENTER}}`, `{{CELL_HEADER_RIGHT}}`
- `{{CELL_TOP_LEFT}}`, `{{CELL_TOP_CENTER}}`, `{{CELL_TOP_RIGHT}}`
- `{{CELL_MIDDLE_LEFT}}`, `{{CELL_MIDDLE_CENTER}}`, `{{CELL_MIDDLE_RIGHT}}`
- `{{CELL_BOTTOM_LEFT}}`, `{{CELL_BOTTOM_CENTER}}`, `{{CELL_BOTTOM_RIGHT}}`

사용 예:

```bash
md2hwpx input.md --reference-doc=my_template.hwpx -o output.hwpx
```

### 방법 2: 스타일 직접 편집

1. 기본 템플릿 복사:
   ```bash
   python -c "import md2hwpx; import shutil; shutil.copy(md2hwpx.__path__[0] + '/blank.hwpx', 'my_template.hwpx')"
   ```
2. 한컴오피스에서 **서식 > 스타일(F6)** 메뉴로 편집
3. 참조 템플릿으로 사용

## 지원하는 마크다운 요소

| 요소 | 지원 |
|------|------|
| 제목 (1–9) | 지원 |
| 문단 | 지원 |
| 굵게 / 기울임 / 취소선 | 지원 |
| 링크 | 지원 (HWPX 하이퍼링크) |
| 이미지 | 지원 (임베딩) |
| 표 (GFM) | 지원 (정렬 + 컬럼 비율) |
| 글머리/번호 목록 | 지원 (중첩) |
| 코드 블록 | 지원 |
| 인라인 코드 | 지원 |
| 인용문 | 지원 (중첩) |
| 수평선 | 지원 |
| 각주 | 지원 |
| 위첨자 / 아래첨자 | AST에 있으면 출력 지원 |

## 보안 및 제한 사항

- 입력/템플릿 파일 크기 제한 (기본 50 MB)
- 이미지 개수 제한 (기본 500)
- 이미지 경로 검증(절대 경로/상위 경로 차단)

## 개발

```bash
# 개발 설치
pip install -e .

# 테스트 실행
python -m pytest tests/ -v

# 자세한 로그로 실행
md2hwpx test.md -o output.hwpx --verbose
```

## 포크 이후 변경 사항

원본 포크 이후 주요 변경 사항:

- 헤더/리스트/표 셀 플레이스홀더 기반 스타일
- GFM 표 정렬 및 컬럼 비율 처리
- 프론트매터 메타데이터(title) 반영
- 리스트 시작 번호 및 템플릿 번호 매기기 개선
- 보안 제한(파일 크기, 이미지 개수, 경로 검증)

## 라이선스

MIT License. 자세한 내용은 `LICENSE`를 참고하세요.
