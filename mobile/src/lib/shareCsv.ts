/* Hand a table to the phone's share sheet as a .csv file (WhatsApp, Mail, Drive, Excel…). In a browser it downloads
   the file like the website does. */
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";
import { toCsv } from "./csv";
import type { TableData } from "./types";

const BOM = "﻿"; // so Excel reads ₹ and other non-ASCII text as UTF-8

export async function shareCsv(name: string, table: TableData): Promise<void> {
  const csv = BOM + toCsv(table);
  const filename = `${name}.csv`;
  if (Platform.OS === "web") {
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  const file = new File(Paths.cache, filename);
  file.create({ overwrite: true });
  await file.write(csv);
  await Sharing.shareAsync(file.uri, { mimeType: "text/csv", UTI: "public.comma-separated-values-text", dialogTitle: filename });
}
