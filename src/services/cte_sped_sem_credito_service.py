from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "{http://www.portalfiscal.inf.br/cte}"


def _txt(parent, tag: str, default: str = "") -> str:
    if parent is None:
        return default
    el = parent.find(NS + tag)
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _money(value: str | Decimal | None) -> str:
    if value in (None, ""):
        return ""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        d = Decimal("0")
    return f"{d:.2f}".replace(".", ",")


def _date_sped(iso_datetime: str) -> str:
    if not iso_datetime:
        return ""
    # CT-e normally uses ISO 8601 date-time. Keep just the date component.
    return datetime.strptime(iso_datetime[:10], "%Y-%m-%d").strftime("%d%m%Y")


def _line(fields: list[str]) -> str:
    return "|" + "|".join("" if x is None else str(x) for x in fields) + "|"


def _reg(line: str) -> str:
    p = line.split("|")
    return p[1] if len(p) > 1 else ""


def _cfop_entrada(cfop_xml: str) -> str:
    if len(cfop_xml) != 4 or not cfop_xml.isdigit():
        raise ValueError(f"CFOP inválido no XML: {cfop_xml!r}")
    m = {"5": "1", "6": "2", "7": "3"}
    if cfop_xml[0] not in m:
        raise ValueError(f"CFOP de prestação não reconhecido para conversão em aquisição: {cfop_xml}")
    return m[cfop_xml[0]] + cfop_xml[1:]


def _cst_sem_credito(cst_xml: str) -> str:
    """CST sob enfoque do declarante quando o crédito de entrada não será apropriado.

    - CST 40/41/50/51/60 já representam situações sem crédito destacado/aproveitável e são preservados.
    - Demais situações tributadas são escrituradas como 090 (Outras) para deixar explícito o não crédito.
    O primeiro caractere do CST do D190 deve ser 0 para serviços de transporte.
    """
    cst = (cst_xml or "90").zfill(2)[-2:]
    if cst in {"40", "41", "50", "51", "60"}:
        return "0" + cst
    return "090"


@dataclass
class Emitente:
    cnpj: str
    nome: str
    ie: str
    cod_mun: str
    logradouro: str
    numero: str
    complemento: str
    bairro: str


@dataclass
class CTe:
    chave: str
    dh_emi: str
    serie: str
    numero: str
    tp_cte: str
    cfop_xml: str
    cfop_sped: str
    cst_xml: str
    cst_sped: str
    valor: Decimal
    bc_original: Decimal
    icms_original: Decimal
    emit: Emitente
    cod_mun_ini: str
    cod_mun_fim: str
    toma_role: str


def _parse_sped(sped_path: Path):
    raw = sped_path.read_bytes()
    encoding = "utf-8"
    for enc in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            text = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    lines = text.splitlines()
    if not lines:
        raise ValueError("SPED vazio")

    rec0000 = next((x for x in lines if x.startswith("|0000|")), None)
    if rec0000 is None:
        raise ValueError("Registro 0000 não encontrado")
    p = rec0000.split("|")
    cnpj = re.sub(r"\D", "", p[7])
    dt_ini = p[4]
    dt_fin = p[5]
    return lines, encoding, cnpj, dt_ini, dt_fin


def _existing_participants(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if not line.startswith("|0150|"):
            continue
        p = line.split("|")
        if len(p) > 5 and p[5]:
            cnpj = re.sub(r"\D", "", p[5])
            out.setdefault(cnpj, p[2])
    return out


def _existing_cte_keys(lines: list[str]) -> set[str]:
    keys = set()
    for line in lines:
        if line.startswith("|D100|"):
            p = line.split("|")
            if len(p) > 10 and p[10]:
                keys.add(p[10])
    return keys


def _tomador(inf, cnpj_declarante: str):
    ide = inf.find(NS + "ide")
    emit = inf.find(NS + "emit")
    rem = inf.find(NS + "rem")
    dest = inf.find(NS + "dest")
    exped = inf.find(NS + "exped")
    receb = inf.find(NS + "receb")

    def doc(x):
        return _txt(x, "CNPJ") or _txt(x, "CPF")

    parties = {
        "emit": doc(emit),
        "rem": doc(rem),
        "dest": doc(dest),
        "exped": doc(exped),
        "receb": doc(receb),
    }

    t3 = ide.find(NS + "toma3") if ide is not None else None
    t4 = ide.find(NS + "toma4") if ide is not None else None
    role = ""
    toma_doc = ""
    if t3 is not None:
        role = {"0": "rem", "1": "exped", "2": "receb", "3": "dest"}.get(_txt(t3, "toma"), "")
        toma_doc = parties.get(role, "")
    elif t4 is not None:
        role = "outro"
        toma_doc = _txt(t4, "CNPJ") or _txt(t4, "CPF")
    return toma_doc == cnpj_declarante, role


def _iter_cte_xml_from_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.lower().endswith(".xml"):
                continue
            try:
                data = z.read(name)
                root = ET.fromstring(data)
            except Exception:
                continue
            yield name, root


def _load_ctes(zip_path: Path, cnpj_declarante: str, dt_ini: str, dt_fin: str, existing_keys: set[str]):
    ini = datetime.strptime(dt_ini, "%d%m%Y").date()
    fim = datetime.strptime(dt_fin, "%d%m%Y").date()
    ctes: list[CTe] = []
    skipped = Counter()
    seen = set()

    for name, root in _iter_cte_xml_from_zip(zip_path):
        inf = root.find(".//" + NS + "infCte")
        if inf is None:
            skipped["sem_infCte"] += 1
            continue
        ide = inf.find(NS + "ide")
        if ide is None or _txt(ide, "mod") != "57":
            skipped["modelo_nao_57"] += 1
            continue

        key = (inf.attrib.get("Id") or "").replace("CTe", "")
        if not key:
            skipped["sem_chave"] += 1
            continue
        if key in seen:
            skipped["duplicado_zip"] += 1
            continue
        seen.add(key)
        if key in existing_keys:
            skipped["ja_no_sped"] += 1
            continue

        # Only authorized CT-e.
        infprot = root.find(".//" + NS + "protCTe/" + NS + "infProt")
        if infprot is not None and _txt(infprot, "cStat") != "100":
            skipped["nao_autorizado"] += 1
            continue

        dh_emi = _txt(ide, "dhEmi") or _txt(ide, "dEmi")
        try:
            d = datetime.strptime(dh_emi[:10], "%Y-%m-%d").date()
        except Exception:
            skipped["data_invalida"] += 1
            continue
        if d < ini or d > fim:
            skipped["fora_periodo"] += 1
            continue

        is_tomador, role = _tomador(inf, cnpj_declarante)
        if not is_tomador:
            skipped["declarante_nao_tomador"] += 1
            continue

        emit = inf.find(NS + "emit")
        end = emit.find(NS + "enderEmit") if emit is not None else None
        emitente = Emitente(
            cnpj=_txt(emit, "CNPJ"),
            nome=_txt(emit, "xNome"),
            ie=_txt(emit, "IE"),
            cod_mun=_txt(end, "cMun"),
            logradouro=_txt(end, "xLgr"),
            numero=_txt(end, "nro"),
            complemento=_txt(end, "xCpl"),
            bairro=_txt(end, "xBairro"),
        )

        vp = inf.find(NS + "vPrest")
        valor = Decimal(_txt(vp, "vTPrest", "0") or "0")
        icms = inf.find(".//" + NS + "ICMS")
        icms_child = icms[0] if icms is not None and len(icms) else None
        cst_xml = _txt(icms_child, "CST", "90")
        bc_original = Decimal(_txt(icms_child, "vBC", "0") or "0")
        icms_original = Decimal(_txt(icms_child, "vICMS", "0") or "0")
        cfop_xml = _txt(ide, "CFOP")

        ctes.append(
            CTe(
                chave=key,
                dh_emi=dh_emi,
                serie=_txt(ide, "serie").zfill(3),
                numero=str(int(_txt(ide, "nCT"))),
                tp_cte=_txt(ide, "tpCTe", "0"),
                cfop_xml=cfop_xml,
                cfop_sped=_cfop_entrada(cfop_xml),
                cst_xml=cst_xml,
                cst_sped=_cst_sem_credito(cst_xml),
                valor=valor,
                bc_original=bc_original,
                icms_original=icms_original,
                emit=emitente,
                cod_mun_ini=_txt(ide, "cMunIni"),
                cod_mun_fim=_txt(ide, "cMunFim"),
                toma_role=role,
            )
        )

    ctes.sort(key=lambda x: (x.dh_emi, x.serie, int(x.numero), x.chave))
    return ctes, skipped


def _add_missing_participants(lines: list[str], ctes: list[CTe], participant_by_cnpj: dict[str, str]):
    new_lines = []
    new_emitters: dict[str, Emitente] = {}
    used_codes = {line.split("|")[2] for line in lines if line.startswith("|0150|")}

    for cte in ctes:
        cnpj = cte.emit.cnpj
        if cnpj in participant_by_cnpj:
            continue
        if cnpj in new_emitters:
            continue
        new_emitters[cnpj] = cte.emit

    for cnpj, emit in sorted(new_emitters.items()):
        base = f"CTE_{cnpj}"
        code = base
        n = 2
        while code in used_codes:
            code = f"{base}_{n}"
            n += 1
        used_codes.add(code)
        participant_by_cnpj[cnpj] = code
        new_lines.append(
            _line([
                "0150", code, emit.nome, "1058", emit.cnpj, "", emit.ie,
                emit.cod_mun, "", emit.logradouro, emit.numero,
                emit.complemento, emit.bairro,
            ])
        )

    if new_lines:
        last_0150 = max(i for i, line in enumerate(lines) if line.startswith("|0150|"))
        lines[last_0150 + 1:last_0150 + 1] = new_lines
    return new_lines


def _cte_records(cte: CTe, cod_part: str):
    dt = _date_sped(cte.dh_emi)
    # IND_FRT: declarante is remetente/destinatário and tomador -> 1.
    ind_frt = "1" if cte.toma_role in {"rem", "dest"} else "2"

    d100 = _line([
        "D100",
        "0",            # IND_OPER: aquisição
        "1",            # IND_EMIT: terceiros
        cod_part,
        "57",
        "00",
        cte.serie,
        "",             # SUB
        cte.numero,
        cte.chave,
        dt,
        dt,              # DT_A_P: data de aquisição/prestação, adotada = emissão
        cte.tp_cte,
        "",             # CHV_CTE_REF
        _money(cte.valor),
        "",             # VL_DESC
        ind_frt,
        _money(cte.valor),
        "",             # VL_BC_ICMS - vazio: sem apropriação de crédito
        "",             # VL_ICMS - vazio: sem apropriação de crédito
        "",             # VL_NT
        "",             # COD_INF
        "",             # COD_CTA
        cte.cod_mun_ini,
        cte.cod_mun_fim,
    ])

    d190 = _line([
        "D190",
        cte.cst_sped,
        cte.cfop_sped,
        "",             # ALIQ_ICMS: não informar sem direito/aproveitamento do crédito
        _money(cte.valor),
        "0",
        "0",
        "0",
        "",
    ])
    return [d100, d190]


def _replace_block_d(lines: list[str], ctes: list[CTe], participant_by_cnpj: dict[str, str]):
    i_d001 = next(i for i, x in enumerate(lines) if x.startswith("|D001|"))
    i_d990 = next(i for i, x in enumerate(lines) if x.startswith("|D990|"))
    existing_body = lines[i_d001 + 1:i_d990]

    add = []
    for cte in ctes:
        add.extend(_cte_records(cte, participant_by_cnpj[cte.emit.cnpj]))

    lines[i_d001] = "|D001|0|"
    lines[i_d001 + 1:i_d990] = existing_body + add
    # D990 location changed after splice; find again.
    i_d990 = next(i for i, x in enumerate(lines) if x.startswith("|D990|"))
    qtd_d = i_d990 - i_d001 + 1
    lines[i_d990] = f"|D990|{qtd_d}|"


def _update_0990(lines: list[str]):
    i0 = next(i for i, x in enumerate(lines) if x.startswith("|0000|"))
    i0990 = next(i for i, x in enumerate(lines) if x.startswith("|0990|"))
    lines[i0990] = f"|0990|{i0990 - i0 + 1}|"


def _rebuild_block9(lines: list[str]):
    i9001 = next(i for i, x in enumerate(lines) if x.startswith("|9001|"))
    old_9900 = [x.split("|")[2] for x in lines[i9001 + 1:] if x.startswith("|9900|")]
    prefix = lines[:i9001 + 1]

    counts = Counter(_reg(x) for x in prefix if _reg(x))
    unique_regs = set(counts)
    unique_regs.update({"9900", "9990", "9999"})

    order = []
    for reg in old_9900:
        if reg not in order and reg in unique_regs:
            order.append(reg)
    # Insert newly appearing registers near the relevant block, keeping 9900 last.
    for reg in sorted(unique_regs):
        if reg not in order and reg != "9900":
            if reg.startswith("D"):
                # Keep the natural Block D sequence: D001, details, D990.
                try:
                    idx = order.index("D990")
                except ValueError:
                    try:
                        idx = max(i for i, r in enumerate(order) if r.startswith("D")) + 1
                    except ValueError:
                        idx = len(order)
                order.insert(idx, reg)
            else:
                order.append(reg)
    if "9900" in order:
        order.remove("9900")
    order.append("9900")

    n9900 = len(order)
    counts["9900"] = n9900
    counts["9990"] = 1
    counts["9999"] = 1

    records_9900 = [_line(["9900", reg, str(counts.get(reg, 0))]) for reg in order]
    qtd_lin_9 = 1 + len(records_9900) + 1 + 1
    new_lines = prefix + records_9900 + [f"|9990|{qtd_lin_9}|", "|9999|0|"]
    new_lines[-1] = f"|9999|{len(new_lines)}|"
    return new_lines


def _validate(lines: list[str], ctes: list[CTe]):
    errors = []
    counts = Counter(_reg(x) for x in lines if _reg(x))

    # Block closing counts.
    for closing, start in [("0990", "0000"), ("D990", "D001")]:
        i_start = next(i for i, x in enumerate(lines) if x.startswith(f"|{start}|"))
        i_close = next(i for i, x in enumerate(lines) if x.startswith(f"|{closing}|"))
        got = int(lines[i_close].split("|")[2])
        exp = i_close - i_start + 1
        if got != exp:
            errors.append(f"{closing}: esperado {exp}, encontrado {got}")

    # 9999 total.
    total = int(lines[-1].split("|")[2]) if lines[-1].startswith("|9999|") else -1
    if total != len(lines):
        errors.append(f"9999: esperado {len(lines)}, encontrado {total}")

    # D100/D190 relationships for inserted CT-e.
    d100 = [x for x in lines if x.startswith("|D100|")]
    d190 = [x for x in lines if x.startswith("|D190|")]
    if len(d100) < len(ctes) or len(d190) < len(ctes):
        errors.append("Quantidade de D100/D190 menor que a quantidade de CT-e incluídos")

    participants = {x.split("|")[2] for x in lines if x.startswith("|0150|")}
    for x in d100:
        p = x.split("|")
        if p[4] not in participants:
            errors.append(f"D100 com COD_PART inexistente: {p[4]}")
        if p[2] == "0" and p[3] == "1" and p[5] == "57":
            # acquisition / third-party / model 57
            if p[19] or p[20]:
                errors.append(f"D100 de entrada com crédito preenchido: chave {p[10]}")

    # Validate 9900 counts.
    actual = Counter(_reg(x) for x in lines if _reg(x))
    for x in lines:
        if x.startswith("|9900|"):
            p = x.split("|")
            reg, qtd = p[2], int(p[3])
            if actual[reg] != qtd:
                errors.append(f"9900 {reg}: esperado {actual[reg]}, informado {qtd}")

    return errors


def process(sped_path: Path | str, cte_zip: Path | str, out_path: Path | str, report_path: Path | str):
    sped_path = Path(sped_path)
    cte_zip = Path(cte_zip)
    out_path = Path(out_path)
    report_path = Path(report_path)
    lines, encoding, cnpj, dt_ini, dt_fin = _parse_sped(sped_path)
    participant_by_cnpj = _existing_participants(lines)
    existing_keys = _existing_cte_keys(lines)

    ctes, skipped = _load_ctes(cte_zip, cnpj, dt_ini, dt_fin, existing_keys)
    new_participants = _add_missing_participants(lines, ctes, participant_by_cnpj)
    _update_0990(lines)
    _replace_block_d(lines, ctes, participant_by_cnpj)
    lines = _rebuild_block9(lines)

    errors = _validate(lines, ctes)
    if errors:
        raise RuntimeError("Falha na validação estrutural:\n- " + "\n- ".join(errors[:50]))

    # SPED files are commonly consumed safely as Latin-1/ANSI in desktop validators.
    out_path.write_text("\r\n".join(lines) + "\r\n", encoding="latin-1", errors="replace")

    with report_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "CHAVE_CTE", "DATA_EMISSAO", "CNPJ_EMITENTE", "EMITENTE", "SERIE", "NUMERO",
            "CFOP_XML", "CFOP_SPED", "CST_XML", "CST_SPED_SEM_CREDITO", "VALOR_PRESTACAO",
            "BASE_ICMS_XML", "ICMS_XML_NAO_APROPRIADO", "CREDITO_SPED"
        ])
        for c in ctes:
            w.writerow([
                c.chave, _date_sped(c.dh_emi), c.emit.cnpj, c.emit.nome, c.serie, c.numero,
                c.cfop_xml, c.cfop_sped, c.cst_xml, c.cst_sped, _money(c.valor),
                _money(c.bc_original), _money(c.icms_original), "0,00"
            ])

    summary = {
        "cnpj": cnpj,
        "periodo": f"{dt_ini}-{dt_fin}",
        "ctes_incluidos": len(ctes),
        "participantes_adicionados": len(new_participants),
        "valor_frete": sum((c.valor for c in ctes), Decimal("0")),
        "base_original": sum((c.bc_original for c in ctes), Decimal("0")),
        "icms_original_nao_apropriado": sum((c.icms_original for c in ctes), Decimal("0")),
        "skipped": dict(skipped),
        "linhas_saida": len(lines),
    }
    return summary


def main():
    ap = argparse.ArgumentParser(description="Inclui CT-e ausentes no SPED Fiscal sem apropriar crédito de ICMS.")
    ap.add_argument("--sped", required=True, type=Path)
    ap.add_argument("--cte", required=True, type=Path, help="ZIP com XMLs de CT-e")
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--relatorio", required=True, type=Path)
    args = ap.parse_args()
    s = process(args.sped, args.cte, args.saida, args.relatorio)
    print("OK")
    for k, v in s.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
