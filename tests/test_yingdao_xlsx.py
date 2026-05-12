import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from falcon.adapters.yingdao_xlsx import YingdaoXlsxAdapter
from falcon.cli import main
from falcon.db import FalconRepository


def write_minimal_xlsx(path: Path, rows):
    def cell_ref(row_number, column_number):
        column = chr(ord("A") + column_number)
        return f"{column}{row_number}"

    row_xml = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column_number, value in enumerate(row):
            escaped = (
                str(value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            cells.append(
                f'<c r="{cell_ref(row_number, column_number)}" t="inlineStr">'
                f"<is><t>{escaped}</t></is></c>"
            )
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(row_xml)}</sheetData>
</worksheet>""",
        )


class YingdaoXlsxAdapterTest(unittest.TestCase):
    def test_loads_yingdao_two_column_export_with_keyword_from_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "xhs_raw_export.xlsx"
            write_minimal_xlsx(
                xlsx_path,
                [
                    ["A", "B"],
                    ["想做好内容？封面真的不能随便！", "https://www.xiaohongshu.com/search_result/1"],
                    ["", "https://www.xiaohongshu.com/search_result/blank"],
                    ["没有链接的标题", ""],
                ],
            )

            items = YingdaoXlsxAdapter().load(xlsx_path, keyword="生图小程序")

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].platform, "xiaohongshu")
            self.assertEqual(items[0].keyword, "生图小程序")
            self.assertEqual(items[0].source_type, "post")
            self.assertEqual(items[0].title, "想做好内容？封面真的不能随便！")
            self.assertEqual(items[0].content, "想做好内容？封面真的不能随便！")
            self.assertEqual(items[0].url, "https://www.xiaohongshu.com/search_result/1")
            self.assertEqual(items[0].published_at, "")

    def test_loads_yingdao_structured_post_and_comment_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "xhs_structured_export.xlsx"
            write_minimal_xlsx(
                xlsx_path,
                [
                    [
                        "platform",
                        "keyword",
                        "source_type",
                        "title",
                        "content",
                        "url",
                        "parent_url",
                        "author",
                        "commenter",
                        "like_count",
                        "comment_rank",
                        "collected_at",
                    ],
                    [
                        "xiaohongshu",
                        "生图小程序",
                        "post",
                        "生图工具测评",
                        "这篇笔记正文里提到小红书封面和活动海报怎么做。",
                        "https://www.xiaohongshu.com/explore/post1",
                        "",
                        "作者A",
                        "",
                        "18",
                        "",
                        "2026-05-12T08:00:00+00:00",
                    ],
                    [
                        "xiaohongshu",
                        "生图小程序",
                        "comment",
                        "生图工具测评",
                        "现在这个生图工具不好用，求推荐更好用的生图工具",
                        "https://www.xiaohongshu.com/explore/post1?comment=1",
                        "https://www.xiaohongshu.com/explore/post1",
                        "",
                        "用户B",
                        "25",
                        "1",
                        "2026-05-12T08:01:00+00:00",
                    ],
                ],
            )

            items = YingdaoXlsxAdapter().load(xlsx_path, keyword="兜底关键词")

            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].keyword, "生图小程序")
            self.assertEqual(items[0].source_type, "post")
            self.assertEqual(items[0].content, "这篇笔记正文里提到小红书封面和活动海报怎么做。")
            self.assertEqual(items[0].author, "作者A")
            self.assertEqual(items[1].source_type, "comment")
            self.assertEqual(items[1].parent_url, "https://www.xiaohongshu.com/explore/post1")
            self.assertEqual(items[1].commenter, "用户B")
            self.assertEqual(items[1].like_count, "25")
            self.assertEqual(items[1].comment_rank, "1")

    def test_cli_imports_yingdao_xlsx_with_keyword_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            xlsx_path = tmp_path / "xhs_raw_export.xlsx"
            db_path = tmp_path / "falcon.sqlite3"
            write_minimal_xlsx(
                xlsx_path,
                [["想做好内容？封面真的不能随便！", "https://www.xiaohongshu.com/search_result/1"]],
            )

            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-yingdao-xlsx",
                        str(xlsx_path),
                        "--keyword",
                        "生图小程序",
                    ]
                )

            items = FalconRepository(db_path).list_raw_items()
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].keyword, "生图小程序")
            self.assertEqual(items[0].title, "想做好内容？封面真的不能随便！")


if __name__ == "__main__":
    unittest.main()
