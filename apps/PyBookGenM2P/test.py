from api import markdown_to_pdf, m2p_apis

for api in m2p_apis:
    ret = markdown_to_pdf("./test.md", "./out/test_{}.pdf".format(api), api, pandoc_internal=False)
    print(ret)
