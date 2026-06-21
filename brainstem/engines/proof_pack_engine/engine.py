from brainstem.utils.paths import GENERATED

def create(product_id):
    d=GENERATED/'proof_packets'/product_id; d.mkdir(parents=True,exist_ok=True)
    p=d/'proof_packet.md'
    p.write_text('# Proof Packet\n\nMOCK/local evidence only unless external records are attached.\n\nNext required actions: attach evidence.\n',encoding='utf-8')
    return p
