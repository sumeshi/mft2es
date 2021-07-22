# coding: utf-8

# def mft2json(filepath: str) -> List[dict]:
#     """Convert mft to json.
# 
#     Args:
#         filepath (str): Input MFT file.
# 
#     Note:
#         Since the content of the file is loaded into memory at once,
#         it requires the same amount of memory as the file to be loaded.
#     """
#     r = Mft2es(filepath)
# 
#     buffer: List[dict] = sum(list(tqdm(r.gen_records(500))), list())
#     return buffer
