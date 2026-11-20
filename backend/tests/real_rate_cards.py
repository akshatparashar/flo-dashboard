"""The NEW RATE SHEET tab of FABRIC PO 11 as read from the sheet (data rows verbatim; vendor-name and header rows
rebuilt from the sheet's own header text, because the export types columns and drops text in numeric columns)."""
DATA = """1|CREPE|205|250|||1| MUSLINE|165|200||1|CREPE|210|250|
2|MUL CHANDERI|195|240|||2| MUSLINE PRINTED DUPATTA|160|210||2|BEMBER RUSSION SILK|250||
3|BASIC SILK|170|195|||3|CREPE|232|295||3|MUSLIN|145|180|
4|CLASSIC SILK|175|200|||4|SANTOON (DYED)|90|||4|MUL CHANDERI||225|
5|RUSSIAN SILK |200|230|||5|HAND WORK PR PC|120|||5|ORGENZA (PRINTED)||235|
6|CHINON|185|235|||6|CREPE HAND WORK PR PC|160|||6| DIG. 60*60 COTTON |135||
7| VISCOSE MUSLINE|165|195|||7|MUSLIN PRINT HAND WORK PR PC|120/125|||7|DIG.VISCOS ORGENZA||220|225
8|PLAIN ORGENZA|80|120|||8|CHINON DUPATTA MTR|220|275|||||
9|PLAIN CREPE|0|125|||||||||||
10|PLAIN CHINON|72|115||||||||||||
11|ORGANZA PRINTED|185|235||||||||||||
12|SUPER COTTON (DIGITAL PRINT)|145|170|||1| MUSLINE|160|185||1|FLEX LILEN||132|
13|DOBBY||200|||2|CREPE|220|265||2|FLEX LILEN DUPATTA (PER PC)|145||
||||||3|ORGENZA||220||3|FLEX WRINKLE SWISS||142|
||||||4|RUSSIAN SILK |185|||||||
||||||5|CHINON SIFON|180|230||||||
||||||||||||||||
1|REMI SILK|175|230||||||||1|PLAIN ORGENZA|85|135|
2|NATURAL CREPE|230|280||||||||2|MUSLIN|165|200|
3|SAND CREPE|210|280||||||||||||
||||||1|CHANDERI DIG.TOP/DUP.|390|||||||
||||||2|LILEN DIG.TOP/DUP.|435|||||||
||||||3|MODAL DAYED DIG.TOP/DUP.|675|||1|MUL CHANDERI|175|210|
||||||4|MOONGA DIG.TOP/DUP. JAMDANI|675|||2|COTTON ||155|
1|N-CREPE|210|260|||5|MOONGA FLEB DIG.TOP/DUP. JAMDANI|565|||||||
2|MUSLIN|160|200||||||||||||
3|DIG. COTTON|160|200||||||||||||
4|RFD CREPE |120|||||||||1|CHIKU CHANDERI||85|73
|||||||||||2|MUSLIN|||
|||||||||||3|COTTON SILK|||
|||||||||||4|GAJJI SILK|||"""


def grid():
    rows = [[(float(x) if x.replace(".", "", 1).isdigit() else x) if x != "" else "" for x in line.split("|")]
            for line in DATA.split("\n")]
    rows = [r + [""] * (16 - len(r)) for r in rows]
    for r in rows:
        for i, v in enumerate(r):
            if isinstance(v, float) and v == int(v):
                r[i] = int(v)
    hdr = lambda c, cols: {c + i: h for i, h in enumerate(cols)}        # noqa: E731
    five = ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "36 WIDTH"]
    four = ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH"]
    four_v = ["S. NO.", "FABRIC", "36 WIDTH", "60 WIDTH"]
    # (row of the vendor name, column, vendor, header cells): the header goes on the next row, in place
    blocks = [(9, 6, "VIPUL", four), (9, 11, "SHREE SANTINATH", four), (15, 0, "SWAGAT", four),
              (15, 11, "VEDANSHI", four_v), (18, 6, "EKTA FABRIC", ["S. NO.", "FABRIC", "44/36 WIDTH", "60 WIDTH"]),
              (20, 11, "BSK", four), (22, 0, "GOKUL", four), (25, 11, "K THREE PLUS", five)]
    out = [r[:] for r in rows]
    for vrow, col, vendor, cols in blocks:
        out[vrow][col] = vendor
        for k, h in hdr(col, cols).items():
            out[vrow + 1][k] = h
    top = [[""] * 16, [""] * 16]                       # RV / VARSHA / VINAYAK sit above the first data row
    for col, vendor, cols in ((0, "RV", five), (6, "VARSHA", four), (11, "VINAYAK", five)):
        top[0][col] = vendor
        for k, h in hdr(col, cols).items():
            top[1][k] = h
    out = top + out
    return out
