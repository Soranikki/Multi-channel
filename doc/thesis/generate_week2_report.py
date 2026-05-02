from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUTPUT_PATH = Path("/home/soranikki/odoo-dev/Multi-channel/doc/thesis/Bao_cao_tuan_2.docx")


def xml_text(text: str) -> str:
    return escape(text).replace("\n", "&#10;")


def run(text: str, bold: bool = False, italic: bool = False) -> str:
    props = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f"<w:r>{rpr}<w:t xml:space=\"preserve\">{xml_text(text)}</w:t></w:r>"


def paragraph(
    text: str = "",
    *,
    style: str | None = None,
    align: str | None = None,
    page_break_before: bool = False,
    page_break_after: bool = False,
    spacing_before: int | None = None,
    spacing_after: int | None = None,
    keep_next: bool = False,
) -> str:
    ppr_bits: list[str] = []
    if style:
        ppr_bits.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr_bits.append(f'<w:jc w:val="{align}"/>')
    if page_break_before:
        ppr_bits.append("<w:pageBreakBefore/>")
    if keep_next:
        ppr_bits.append("<w:keepNext/>")
    if spacing_before is not None or spacing_after is not None:
        before = spacing_before if spacing_before is not None else 0
        after = spacing_after if spacing_after is not None else 0
        ppr_bits.append(f'<w:spacing w:before="{before}" w:after="{after}"/>')
    ppr = f"<w:pPr>{''.join(ppr_bits)}</w:pPr>" if ppr_bits else ""
    runs = run(text) if text else ""
    if page_break_after:
        runs += '<w:r><w:br w:type="page"/></w:r>'
    return f"<w:p>{ppr}{runs}</w:p>"


def bullet(text: str) -> str:
    return paragraph(f"- {text}", style="BodyText")


def numbered(text: str) -> str:
    return paragraph(text, style="BodyText")


def table_cell(text: str, width: int, bold: bool = False, center: bool = False) -> str:
    align = '<w:jc w:val="center"/>' if center else '<w:jc w:val="both"/>'
    cell_paragraph = (
        f"<w:p><w:pPr><w:pStyle w:val=\"TableText\"/>{align}</w:pPr>{run(text, bold=bold)}</w:p>"
    )
    return (
        f"<w:tc><w:tcPr><w:tcW w:w=\"{width}\" w:type=\"dxa\"/></w:tcPr>"
        f"{cell_paragraph}</w:tc>"
    )


def table(rows: list[list[tuple[str, int, bool, bool]]]) -> str:
    row_xml: list[str] = []
    for row in rows:
        cells = "".join(table_cell(text, width, bold, center) for text, width, bold, center in row)
        row_xml.append(f"<w:tr>{cells}</w:tr>")
    borders = "".join(
        [
            '<w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>',
            '<w:left w:val="single" w:sz="8" w:space="0" w:color="000000"/>',
            '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>',
            '<w:right w:val="single" w:sz="8" w:space="0" w:color="000000"/>',
            '<w:insideH w:val="single" w:sz="6" w:space="0" w:color="000000"/>',
            '<w:insideV w:val="single" w:sz="6" w:space="0" w:color="000000"/>',
        ]
    )
    return (
        '<w:tbl>'
        '<w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
        f'{borders}'
        '</w:tblBorders></w:tblPr>'
        '<w:tblGrid>'
        '<w:gridCol w:w="1100"/><w:gridCol w:w="2600"/><w:gridCol w:w="7200"/>'
        '</w:tblGrid>'
        f"{''.join(row_xml)}"
        '</w:tbl>'
    )


def build_document() -> str:
    elements: list[str] = []

    elements.extend(
        [
            paragraph("TRUONG DAI HOC THUY LOI", style="TitleCenter", align="center", spacing_after=80),
            paragraph("KHOA CONG NGHE THONG TIN", style="TitleCenter", align="center", spacing_after=420),
            paragraph("BAO CAO TIEN DO TUAN 2", style="MainTitle", align="center", spacing_after=160),
            paragraph(
                "PHAN TICH YEU CAU, DAC TA CHUC NANG, USE CASE VA THIET KE KIEN TRUC TONG THE",
                style="SubTitle",
                align="center",
                spacing_after=520,
            ),
            paragraph(
                "De tai: Xay dung he thong quan ly, phan tich du lieu ban hang tu cac trang thuong mai dien tu",
                style="BodyCenter",
                align="center",
                spacing_after=180,
            ),
            paragraph("Sinh vien thuc hien: Tran Gia Khanh", style="BodyCenter", align="center", spacing_after=60),
            paragraph("Lop: 64KTPM3", style="BodyCenter", align="center", spacing_after=60),
            paragraph("Ma sinh vien: 2251172388", style="BodyCenter", align="center", spacing_after=60),
            paragraph("Giang vien huong dan: TS. Ta Quang Chieu", style="BodyCenter", align="center", spacing_after=900),
            paragraph("Ha Noi, 2026", style="BodyCenter", align="center", page_break_after=True),
        ]
    )

    elements.extend(
        [
            paragraph("1. Muc tieu cua giai doan tuan 2", style="Heading1", keep_next=True),
            paragraph(
                "Trong giai doan tuan 2, de tai tap trung vao viec phan tich yeu cau nghiep vu va ky thuat, xac dinh pham vi trien khai, xay dung dac ta chuc nang, mo hinh use case va de xuat kien truc tong the cho he thong. Ket qua cua giai doan nay la co so de chuyen sang buoc thiet ke chi tiet va trien khai cac module trong nhung tuan tiep theo.",
                style="BodyText",
            ),
            paragraph("2. Phan tich bai toan", style="Heading1", keep_next=True),
            paragraph(
                "Trong mo hinh kinh doanh da kenh, du lieu ban hang thuong bi phan tan tren nhieu nen tang nhu Shopee va TikTok Shop. Moi san co cach bieu dien du lieu rieng cho san pham, don hang, ton kho va trang thai giao dich, dan den kho khan trong viec tong hop va doi soat du lieu. Viec cap nhat ton kho thu cong giua cac kenh de gay sai sot, cham tre va co nguy co xay ra tinh trang ban vuot muc ton kho thuc te.",
                style="BodyText",
            ),
            paragraph(
                "Tu bai toan thuc te do, he thong duoc de xuat se dong vai tro la mot nen tang quan ly tap trung, cho phep tiep nhan du lieu tu cac san thuong mai dien tu thong qua API, chuan hoa ve mot cau truc thong nhat, thuc hien anh xa ma san pham, cap nhat bien dong ton kho va cung cap cac bao cao phan tich doanh thu, hieu suat kinh doanh. Odoo duoc lua chon lam he thong trung tam quan ly du lieu va quy trinh nghiep vu, trong khi middleware dam nhiem vai tro ket noi va dong bo du lieu voi cac nen tang ben ngoai.",
                style="BodyText",
            ),
            paragraph("3. Pham vi de tai", style="Heading1", keep_next=True),
            paragraph("3.1. Pham vi chuc nang", style="Heading2", keep_next=True),
            bullet("Quan ly danh muc san pham noi bo va ma san pham noi bo."),
            bullet("Quan ly ton kho tap trung va lich su bien dong ton kho."),
            bullet("Quan ly don hang dong bo tu nhieu kenh ban hang."),
            bullet("Tich hop du lieu tu Shopee va TikTok Shop thong qua API va middleware."),
            bullet("Chuan hoa du lieu tho va anh xa ma san pham giua he thong noi bo voi tung san."),
            bullet("Dong bo ton kho hai chieu va ho tro giam thieu tinh trang overselling."),
            bullet("Cung cap dashboard thong ke doanh thu, don hang va canh bao ton kho."),
            paragraph("3.2. Ngoai pham vi hoac chi mo phong trong do an", style="Heading2", keep_next=True),
            bullet("Thanh toan truc tuyen va doi soat voi cong thanh toan."),
            bullet("Tich hop van chuyen thuc te voi cac don vi giao hang."),
            bullet("Mo rong sang nhieu san khac ngoai Shopee va TikTok Shop trong giai doan dau."),
            bullet("Trien khai day du tat ca phan he ERP cua Odoo."),
            paragraph("4. Doi tuong su dung he thong", style="Heading1", keep_next=True),
            paragraph("He thong huong toi bon nhom tac nhan chinh sau day:", style="BodyText"),
            bullet("Quan tri vien: cau hinh he thong, quan ly ket noi API, phan quyen va giam sat hoat dong dong bo."),
            bullet("Nhan vien van hanh: theo doi san pham, ton kho, don hang va xu ly cac truong hop anh xa du lieu chua chinh xac."),
            bullet("Nguoi quan ly: khai thac dashboard, bao cao doanh thu, ton kho va cac chi so kinh doanh de ho tro ra quyet dinh."),
            bullet("San thuong mai dien tu: dong vai tro he thong ben ngoai cung cap du lieu va nhan cap nhat ton kho nguoc tu he thong trung tam."),
            paragraph("5. Yeu cau chuc nang", style="Heading1", keep_next=True),
            bullet("He thong phai ho tro tao, sua, tra cuu san pham noi bo va luu thong tin SKU trung tam."),
            bullet("He thong phai ghi nhan, cap nhat va hien thi ton kho hien tai, ton kho du tru va lich su bien dong ton kho."),
            bullet("He thong phai tiep nhan don hang tu cac san va luu cac thong tin nhu ma don hang, thoi gian dat, trang thai, tong tien va danh sach san pham."),
            bullet("He thong phai luu du lieu tho nhan tu middleware de dam bao kha nang truy vet va phuc vu kiem tra khi co sai lech."),
            bullet("He thong phai chuan hoa du lieu tu nhieu san ve mot cau truc du lieu thong nhat de xu ly tap trung."),
            bullet("He thong phai ho tro anh xa giua ma san pham tren san va ma san pham noi bo, bao gom ca truong hop xu ly thu cong."),
            bullet("He thong phai cap nhat ton kho dua tren don hang phat sinh va co co che dong bo nguoc ton kho len cac san khi co thay doi."),
            bullet("He thong phai cung cap giao dien dashboard de thong ke doanh thu theo san, so luong don hang, ton kho va canh bao mat hang sap het."),
            paragraph("6. Yeu cau phi chuc nang", style="Heading1", keep_next=True),
            bullet("Du lieu phai dam bao tinh nhat quan, han che trung lap va co kha nang truy xuat nguon goc."),
            bullet("Kien truc he thong phai co tinh mo rong de co the bo sung them kenh ban hang trong tuong lai."),
            bullet("He thong can co co che phan quyen ro rang giua nguoi quan tri, nhan vien van hanh va nguoi quan ly."),
            bullet("Viec ket noi API va trao doi du lieu voi middleware phai dam bao an toan thong tin."),
            bullet("He thong can dap ung duoc quy mo du lieu cua mot cua hang vua va nho trong pham vi do an va co giao dien de su dung trong moi truong nghiep vu."),
            paragraph("7. Dac ta chuc nang tong quat", style="Heading1", keep_next=True),
        ]
    )

    elements.append(
        table(
            [
                [("Ma", 1100, True, True), ("Ten chuc nang", 2600, True, True), ("Mo ta", 7200, True, True)],
                [("F01", 1100, False, True), ("Quan ly san pham", 2600, False, False), ("Quan ly danh muc san pham noi bo, SKU, thong tin nhan dien va trang thai hoat dong.", 7200, False, False)],
                [("F02", 1100, False, True), ("Quan ly ton kho", 2600, False, False), ("Theo doi ton kho hien tai, ton du tru, bien dong tang giam va canh bao ton kho thap.", 7200, False, False)],
                [("F03", 1100, False, True), ("Quan ly don hang", 2600, False, False), ("Luu tru va xu ly don hang dong bo tu cac san thuong mai dien tu trong he thong trung tam.", 7200, False, False)],
                [("F04", 1100, False, True), ("Tich hop API", 2600, False, False), ("Tiep nhan du lieu tu middleware va cac nen tang ben ngoai thong qua giao tiep API.", 7200, False, False)],
                [("F05", 1100, False, True), ("Chuan hoa du lieu", 2600, False, False), ("Chuyen du lieu tho ve mot mo hinh du lieu thong nhat de xu ly tap trung va truy vet.", 7200, False, False)],
                [("F06", 1100, False, True), ("Anh xa san pham", 2600, False, False), ("Lien ket ma san pham tren tung san voi san pham noi bo, phuc vu dong bo va doi soat.", 7200, False, False)],
                [("F07", 1100, False, True), ("Dong bo ton kho", 2600, False, False), ("Cap nhat ton kho hai chieu giua he thong trung tam va cac kenh ban hang, ho tro giam overselling.", 7200, False, False)],
                [("F08", 1100, False, True), ("Dashboard bao cao", 2600, False, False), ("Tong hop thong ke doanh thu, don hang, ton kho va cac chi so kinh doanh theo kenh.", 7200, False, False)],
            ]
        )
    )

    elements.extend(
        [
            paragraph("8. Use case tong quat", style="Heading1", keep_next=True, spacing_before=120),
            paragraph("8.1. Tac nhan", style="Heading2", keep_next=True),
            bullet("Quan tri vien"),
            bullet("Nhan vien van hanh"),
            bullet("Nguoi quan ly"),
            bullet("San thuong mai dien tu / Middleware"),
            paragraph("8.2. Danh sach use case chinh", style="Heading2", keep_next=True),
            bullet("Dang nhap he thong"),
            bullet("Quan ly san pham"),
            bullet("Quan ly ton kho"),
            bullet("Quan ly don hang"),
            bullet("Cau hinh ket noi API"),
            bullet("Dong bo du lieu tu san"),
            bullet("Chuan hoa du lieu"),
            bullet("Anh xa ma san pham"),
            bullet("Dong bo ton kho nguoc"),
            bullet("Xem dashboard bao cao"),
            paragraph("8.3. Mo ta mot so use case tieu bieu", style="Heading2", keep_next=True),
            numbered("Use case 1 - Dong bo du lieu tu san: Nguoi dung kich hoat dong bo hoac he thong chay lich tu dong, middleware gui du lieu chuan hoa ve Odoo, he thong luu du lieu tho, thuc hien kiem tra hop le va chuyen sang cau truc du lieu trung tam."),
            numbered("Use case 2 - Anh xa ma san pham: Nhan vien van hanh kiem tra cac SKU ben ngoai chua duoc gan, chon san pham noi bo tuong ung va luu quan he anh xa de cac lan dong bo sau duoc xu ly tu dong."),
            numbered("Use case 3 - Xem dashboard bao cao: Nguoi quan ly truy cap dashboard de theo doi doanh thu theo san, so don hang, ton kho hien tai va cac canh bao van hanh."),
            paragraph("9. Thiet ke kien truc tong the", style="Heading1", keep_next=True),
            paragraph(
                "He thong duoc de xuat theo kien truc tich hop tap trung gom bon lop chinh. Lop thu nhat la cac nguon du lieu ben ngoai bao gom Shopee va TikTok Shop. Lop thu hai la middleware, co nhiem vu ket noi API, tiep nhan du lieu, chuan hoa payload va dong bo voi he thong trung tam. Lop thu ba la Odoo, dong vai tro he thong loi quan ly san pham, ton kho, don hang, doi soat mapping va luu tru du lieu tap trung tren PostgreSQL. Lop thu tu la lop hien thi va phan tich, bao gom giao dien nghiep vu va dashboard bao cao phuc vu quan ly.",
                style="BodyText",
            ),
            paragraph("9.1. Cac thanh phan chinh", style="Heading2", keep_next=True),
            bullet("Nguon du lieu ben ngoai: Shopee API, TikTok Shop API."),
            bullet("Middleware tich hop: FastAPI hoac mot lop trung gian co chuc nang giao tiep API, xac thuc, chuan hoa du lieu va trung chuyen ve Odoo."),
            bullet("He thong trung tam: Odoo 17 voi cac module quan ly san pham, ton kho, don hang, dong bo va phan tich."),
            bullet("Co so du lieu: PostgreSQL luu tru du lieu trung tam va du lieu truy vet."),
            bullet("Lop bao cao: Dashboard doanh thu theo san, bao cao ton kho, canh bao low stock va do tuoi du lieu dong bo."),
            paragraph("9.2. Luong du lieu tong quat", style="Heading2", keep_next=True),
            numbered("Buoc 1: Du lieu phat sinh tren cac san thuong mai dien tu."),
            numbered("Buoc 2: Middleware lay du lieu qua API va chuan hoa ve dinh dang thong nhat."),
            numbered("Buoc 3: Odoo tiep nhan du lieu, luu du lieu tho, xu ly mapping san pham va tao ban ghi don hang chuan hoa."),
            numbered("Buoc 4: He thong cap nhat ton kho, ghi nhan bien dong va neu can thi dong bo ton kho nguoc lai cac san."),
            numbered("Buoc 5: Du lieu da xu ly duoc tong hop de hien thi tren dashboard va cac bao cao quan tri."),
            paragraph("10. Dinh huong mo hinh du lieu muc cao", style="Heading1", keep_next=True),
            paragraph(
                "O muc khai niem, he thong can cac nhom doi tuong du lieu chinh bao gom kenh ban hang, san pham noi bo, bang anh xa san pham, don hang tho, don hang da chuan hoa, dong bien dong ton kho va nhat ky dong bo. Cach thiet ke nay giup dam bao tinh truy vet du lieu tu nguon vao den du lieu nghiep vu cuoi cung, phu hop voi yeu cau xay dung mot Single Source of Truth cho bai toan ban hang da kenh.",
                style="BodyText",
            ),
            paragraph("11. Ket qua dat duoc trong tuan 2", style="Heading1", keep_next=True),
            bullet("Da lam ro bai toan nghiep vu va xac dinh pham vi nghien cuu cua de tai."),
            bullet("Da xac dinh cac doi tuong su dung va cac chuc nang cot loi cua he thong."),
            bullet("Da xay dung bo yeu cau chuc nang va phi chuc nang cho he thong."),
            bullet("Da de xuat tap use case tong quat va mo ta cac use case tieu bieu."),
            bullet("Da thiet ke kien truc tong the theo huong Odoo lam he thong trung tam va middleware lam lop tich hop."),
            bullet("Da tao co so tai lieu de chuyen sang giai doan thiet ke chi tiet o tuan 3."),
            paragraph("12. Ket luan", style="Heading1", keep_next=True),
            paragraph(
                "Ket qua cua tuan 2 cho thay de tai da co du co so ve mat phan tich va thiet ke muc cao. Viec xac dinh ro pham vi, chuc nang, use case va kien truc tong the giup giam rui ro khi trien khai, dong thoi tao nen tang de phat trien cac module nghiep vu, middleware tich hop va dashboard phan tich trong nhung giai doan tiep theo.",
                style="BodyText",
            ),
        ]
    )

    body = "".join(elements)
    sect_pr = (
        '<w:sectPr>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1417" w:right="1134" w:bottom="1417" w:left="1985" w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="708"/>'
        '<w:docGrid w:linePitch="360"/>'
        '</w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 w15 wp14">'
        f'<w:body>{body}{sect_pr}</w:body></w:document>'
    )


def build_styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
        <w:sz w:val="26"/>
        <w:szCs w:val="26"/>
        <w:lang w:val="vi-VN"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr>
        <w:spacing w:line="360" w:lineRule="auto" w:after="120"/>
      </w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="BodyText">
    <w:name w:val="BodyText"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:jc w:val="both"/>
      <w:ind w:firstLine="567"/>
      <w:spacing w:line="360" w:lineRule="auto" w:after="120"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="BodyCenter">
    <w:name w:val="BodyCenter"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:line="360" w:lineRule="auto" w:after="120"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TitleCenter">
    <w:name w:val="TitleCenter"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:line="360" w:lineRule="auto" w:after="120"/>
    </w:pPr>
    <w:rPr>
      <w:b/>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="MainTitle">
    <w:name w:val="MainTitle"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:line="360" w:lineRule="auto" w:after="240"/>
    </w:pPr>
    <w:rPr>
      <w:b/>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="32"/>
      <w:szCs w:val="32"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="SubTitle">
    <w:name w:val="SubTitle"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:line="360" w:lineRule="auto" w:after="160"/>
    </w:pPr>
    <w:rPr>
      <w:b/>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:before="120" w:after="120"/>
    </w:pPr>
    <w:rPr>
      <w:b/>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="Heading2"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:before="80" w:after="80"/>
    </w:pPr>
    <w:rPr>
      <w:b/>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TableText">
    <w:name w:val="TableText"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:spacing w:line="300" w:lineRule="auto" w:after="40"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="24"/>
      <w:szCs w:val="24"/>
    </w:rPr>
  </w:style>
</w:styles>
"""


def build_font_table() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:font w:name="Times New Roman">
    <w:charset w:val="00"/>
    <w:family w:val="roman"/>
    <w:pitch w:val="variable"/>
  </w:font>
</w:fonts>
"""


def build_settings() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="720"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
  <w:compat/>
</w:settings>
"""


def build_theme() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1F497D"/></a:dk2>
      <a:lt2><a:srgbClr val="EEECE1"/></a:lt2>
      <a:accent1><a:srgbClr val="4F81BD"/></a:accent1>
      <a:accent2><a:srgbClr val="C0504D"/></a:accent2>
      <a:accent3><a:srgbClr val="9BBB59"/></a:accent3>
      <a:accent4><a:srgbClr val="8064A2"/></a:accent4>
      <a:accent5><a:srgbClr val="4BACC6"/></a:accent5>
      <a:accent6><a:srgbClr val="F79646"/></a:accent6>
      <a:hlink><a:srgbClr val="0000FF"/></a:hlink>
      <a:folHlink><a:srgbClr val="800080"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont><a:latin typeface="Times New Roman"/></a:majorFont>
      <a:minorFont><a:latin typeface="Times New Roman"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle/></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>
"""


def build_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""


def build_root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def build_document_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
</Relationships>
"""


def build_app_props() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>OpenCode</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <Company>Thuy Loi University</Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>1.0</AppVersion>
</Properties>
"""


def build_core_props() -> str:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Bao cao tien do tuan 2</dc:title>
  <dc:subject>Phan tich yeu cau va kien truc tong the</dc:subject>
  <dc:creator>OpenCode</dc:creator>
  <cp:keywords>thesis, week 2, requirements, use case, architecture</cp:keywords>
  <dc:description>Report for thesis week 2</dc:description>
  <cp:lastModifiedBy>OpenCode</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""


def write_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", build_content_types())
        docx.writestr("_rels/.rels", build_root_rels())
        docx.writestr("docProps/app.xml", build_app_props())
        docx.writestr("docProps/core.xml", build_core_props())
        docx.writestr("word/document.xml", build_document())
        docx.writestr("word/styles.xml", build_styles())
        docx.writestr("word/fontTable.xml", build_font_table())
        docx.writestr("word/settings.xml", build_settings())
        docx.writestr("word/theme/theme1.xml", build_theme())
        docx.writestr("word/_rels/document.xml.rels", build_document_rels())


if __name__ == "__main__":
    write_docx(OUTPUT_PATH)
    print(f"Created {OUTPUT_PATH}")
