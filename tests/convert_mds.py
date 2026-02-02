import sys
import subprocess
import os

MDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mds")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hwpxs")
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
BLANK_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "md2hwpx", "blank.hwpx")

TEMPLATES = [
    ("blank", BLANK_TEMPLATE),
    ("gov", os.path.join(TEMPLATES_DIR, "gov_template.hwpx")),
    ("gov2", os.path.join(TEMPLATES_DIR, "gov_template2.hwpx")),
    ("placeholder", os.path.join(TEMPLATES_DIR, "placeholder-template.hwpx")),
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    md_files = sorted(f for f in os.listdir(MDS_DIR) if f.endswith(".md"))

    for md_file in md_files:
        md_path = os.path.join(MDS_DIR, md_file)
        md_name = os.path.splitext(md_file)[0]

        for template_name, template_path in TEMPLATES:
            output_name = f"{md_name}_{template_name}.hwpx"
            output_path = os.path.join(OUTPUT_DIR, output_name)

            cmd = [sys.executable, "-m", "md2hwpx", md_path, "-r", template_path, "-o", output_path]
            print(f"Converting: {md_file} + {template_name} -> {output_name}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"  FAILED: {result.stderr.strip()}")
            else:
                print(f"  OK")


if __name__ == "__main__":
    main()
