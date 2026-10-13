"""Source list for connectors, controls, crystal and unselected-part references."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from fetch_datasheet import fetch

HIROSE = "https://www.hirose.com/en/product/document?clcode=CL0673-5021-0-51&productname=BM28B0.6-30DS%2f2-0.35V(51)&series=BM28&lang=en&"
HPAGE = "https://www.hirose.com/en/product/p/CL0673-5021-0-51"

DOCS = [
    ("https://gct.co/files/drawings/usb4105.pdf", "connectors/USB4105_drawing.pdf", "USB4105-GF-A", "GCT USB4105 connector drawing, pinout and recommended PCB layout", "https://gct.co/connector/usb4105", ""),
    ("https://gct.co/files/specs/usb4105-spec.pdf", "connectors/USB4105_specification.pdf", "USB4105-GF-A", "GCT USB4105 product specification", "https://gct.co/connector/usb4105", ""),
    ("https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/2019/12/TC2030-IDC-NL-Datasheet-Rev-B.pdf", "connectors/TC2030-IDC-NL_datasheet_footprint.pdf", "TC2030-IDC-NL", "Tag-Connect TC2030-IDC-NL Rev B footprint and cable drawing", "https://www.tag-connect.com/product/tc2030-idc-nl", "J2 is a bare PCB pad/hole pattern; cable pin numbering does not independently define the custom SWD signal assignment."),
    (HIROSE + "documenttype=2DDrawing&documentid=0001121806", "connectors/BM28B0.6-30DS_51_drawing.pdf", "BM28B0.6-30DS/2-0.35V(51)", "Hirose BM28B0.6-30DS/2-0.35V(51) exact connector drawing", HPAGE, ""),
    (HIROSE + "documenttype=SpecSheet&documentid=0001121808", "connectors/BM28B0.6-30DS_51_specification.pdf", "BM28B0.6-30DS/2-0.35V(51)", "Hirose BM28B0.6-30DS/2-0.35V(51) specification", HPAGE, ""),
    (HIROSE + "documenttype=Guideline&documentid=0001442212", "connectors/BM28B0.6-30DS_51_product_guidelines.pdf", "BM28B0.6-30DS/2-0.35V(51)", "Hirose BM28 product handling and assembly guidelines", HPAGE, ""),
    (HIROSE + "documenttype=Catalog&documentid=en_BM28_CAT", "connectors/BM28_series_catalog.pdf", "BM28B0.6-30DS/2-0.35V(51)", "Hirose BM28 series catalog and recommended land patterns", HPAGE, ""),
    ("https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3u.pdf", "controls/B3U_switch_datasheet.pdf", "B3U-3000P", "Omron B3U tactile switch datasheet", "https://components.omron.com/us-en/products/switches/B3U", "Use the B3U-3000P side-actuated, no-ground-terminal, no-boss variant. Alternate official file host used because components.omron.com returned HTTP 403."),
    ("https://fscdn.rohm.com/en/products/databook/datasheet/opto/led/chip_mono/sml-p11mtt86(r)-e.pdf", "controls/SML-P11MTT86R_datasheet.pdf", "SML-P11MTT86R", "ROHM SML-P11MTT86(R) LED datasheet", "https://www.rohm.com/products/led/chip-leds-mono-color-type/standard/sml-p11mt_r_-product", ""),
    ("https://ele.kyocera.com/assets/products/crystal-device/cx3225sa_e.pdf", "sensors_timing/CX3225SA_series_datasheet.pdf", "CX3225SA40000D0PTWCC", "Kyocera CX3225SA crystal series catalog and package drawing", "https://ele.kyocera.com/en/product/crystal-device/crystal_units/cx3225sa/cx3225sa/", "Series-level coverage; confirm the exact 40 MHz ordering-code electrical limits with the exact part specification."),
    ("https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/CX3225SA40000D0PTWCC_5F00_DS.pdf", "sensors_timing/CX3225SA40000D0PTWCC_specification_TI_forum_copy.pdf", "CX3225SA40000D0PTWCC", "Kyocera CX3225SA40000D0PTWCC exact electrical specification (TI forum-hosted copy)", "https://e2e.ti.com/support/sensors-group/sensors/f/sensors-forum/1281050/awr2243-awr2243-casecade-crystal?keymatch=MMWCAS-RF-EVM&tisearch=e2e-sitesearch", "Kyocera-authored exact-MPN specification uploaded by a forum user to TI E2E. Supplemental historical copy, not a current manufacturer-hosted controlled document; official series datasheet archived separately."),
    ("https://data.energizer.com/pdfs/cr2032_eu.pdf", "reference/CR2032_Energizer_reference.pdf", "CR2032 (manufacturer not selected)", "Energizer CR2032 reference datasheet", "https://energizer.com/product/power/specialty/2032-battery/", "Reference candidate only. Project specifies four CR2032 cells but has not selected a battery manufacturer; no BOM substitution made."),
    ("https://www.murata.com/-/media/webrenewal/tool/library/common-pdf/note/note_dynamic-model_i101e.ashx?cvid=20230421010000000000&la=en-gb", "reference/Murata_MLCC_dynamic_model_DC_bias.pdf", "Generic MLCC capacitors (MPNs not selected)", "Murata MLCC dynamic models, DC bias and temperature dependence", "https://article.murata.com/en-us/article/mlcc-dynamic-model-supports-circuit-simulations", "Design reference only; does not establish characteristics of the project's unselected capacitors."),
]

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=5) as pool:
        work = {pool.submit(fetch, *doc): doc for doc in DOCS}
        for future in as_completed(work):
            doc = work[future]
            try:
                result = future.result()
                print("OK", result["path"], result["pages"])
            except Exception as exc:
                print("FAILED", doc[1], str(exc))
