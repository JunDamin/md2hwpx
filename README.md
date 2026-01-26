# md2hwpx

**md2hwpx**는 마크다운(`.md`)을 아래아 한글(`.hwpx`)로 변환해주는 파이썬 도구입니다. Pandoc 없이 순수 파이썬으로 동작합니다.

## 주요 기능

- **입력 형식**: 마크다운(`.md`)
- **출력 형식**: 아래아 한글문서(`.hwpx`)
- **이미지 처리**: 로컬 이미지를 참조하는 마크다운의 경우 이미지를 포함하여 hwpx 생성
- **고급 레이아웃**:
    - 참조용 HWPX 파일(`blank.hwpx`)의 스타일과 페이지 설정(여백 등)을 복제하여 사용합니다.

## 요구 사항

- **Python 3.6+**
- **Python 라이브러리**: marko, python-frontmatter, Pillow

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

## 사용방법

커맨드 라인 도구(`md2hwpx`)를 사용하여 변환합니다.

```sh
# MD -> HWPX
md2hwpx test.md -o output.hwpx

# 참조 문서 지정
md2hwpx test.md --reference-doc=custom.hwpx -o output.hwpx
```

* `--reference-doc`: (선택) 스타일(글자 모양, 문단 모양, 용지 설정 등)을 가져올 기준 HWPX 파일. 지정하지 않으면 패키지에 내장된 기본 파일(`blank.hwpx`)을 사용합니다.

## 스타일 커스터마이징 (Template Customization)

한컴오피스에서 템플릿 HWPX 파일을 편집하여 출력 스타일을 커스터마이징할 수 있습니다.

### 1. 기본 템플릿 복사

```bash
# 패키지에 포함된 blank.hwpx를 복사합니다
python -c "import md2hwpx; import shutil; shutil.copy(md2hwpx.__path__[0] + '/blank.hwpx', 'my_template.hwpx')"
```

### 2. 한컴오피스에서 스타일 편집

1. `my_template.hwpx`를 한컴오피스에서 엽니다
2. **서식 > 스타일** 메뉴 (또는 `F6`)를 선택합니다
3. 원하는 스타일을 수정합니다:

| 스타일 이름 | 마크다운 요소 | 설명 |
|------------|--------------|------|
| 바탕글 | 본문 텍스트 | 일반 문단 |
| 제목 1 | `#` | 1단계 제목 |
| 제목 2 | `##` | 2단계 제목 |
| 제목 3 | `###` | 3단계 제목 |
| 제목 4 | `####` | 4단계 제목 |
| 제목 5 | `#####` | 5단계 제목 |
| 제목 6 | `######` | 6단계 제목 |
| 제목 7 | `#######` | 7단계 제목 |
| 제목 8 | `########` | 8단계 제목 |
| 제목 9 | `#########` | 9단계 제목 |

4. 글꼴, 크기, 색상, 문단 간격, 들여쓰기 등을 수정합니다
5. 저장합니다

### 3. 커스텀 템플릿으로 변환

```bash
md2hwpx input.md --reference-doc=my_template.hwpx -o output.hwpx
```

### 커스터마이징 가능한 항목

- 글꼴 및 크기
- 글자 색상 및 배경색
- 문단 간격 (위/아래 여백, 줄 간격)
- 들여쓰기 및 정렬
- 페이지 여백 및 용지 크기

## 설명 및 제약사항

**md2hwpx**는 [Marko](https://github.com/frostming/marko) 라이브러리를 사용하여 마크다운을 AST(Abstract Syntax Tree)로 파싱한 뒤, 이를 아래아 한글(`.hwpx`) 규격에 맞춰 생성합니다. Pandoc 없이 순수 파이썬으로 동작합니다.

디버깅 및 개발 편의를 위해 중간 단계인 JSON AST 출력 기능을 제공합니다.

```sh
# 디버깅용 JSON 출력
md2hwpx test.md -o debug.json
```

## 예제 (Examples)

프로젝트 내 `tests/` 디렉토리에서 변환된 결과물(`*.hwpx`, `*.html`)과 원본 테스트 파일들을 확인할 수 있습니다.

## 프로젝트 구조

- `md2hwpx/cli.py`: 메인 실행 스크립트.
- `md2hwpx/converter.py`: HWPX 변환 핵심 로직 (AST 파싱, XML 생성, Zip 처리).
- `md2hwpx/blank.hwpx`: HWPX 변환에 필수적인 참조용 템플릿 파일.

## 라이선스 (License)

MIT License. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.
