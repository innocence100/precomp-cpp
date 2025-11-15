import ctypes
import os
import sys
import platform

# ================= 1. 基础配置 =================
system_name = platform.system()
lib_path = ""

if system_name == 'Windows':
    lib_path = os.path.abspath("./precomp_dll_shared.dll") 
elif system_name == 'Linux':
    lib_path = os.path.abspath("./libprecomp_dll_shared.so")
elif system_name == 'Darwin':
    lib_path = os.path.abspath("./libprecomp_dll_shared.dylib")

if not os.path.exists(lib_path):
    print(f"错误: 未找到动态库 {lib_path}")
    sys.exit(1)

try:
    lib = ctypes.CDLL(lib_path)
except OSError as e:
    print(f"加载库失败: {e}")
    sys.exit(1)

# ================= 2. 定义结构体和回调 =================

# 定义 CRecursionContext 结构体，用于设置文件长度
# 对应 libprecomp.h 中的定义
class CRecursionContext(ctypes.Structure):
    _fields_ = [
        ("fin_length", ctypes.c_uint64),        # uintmax_t
        ("anything_was_used", ctypes.c_bool),
        ("non_zlib_was_used", ctypes.c_bool)
    ]

# 回调函数签名
READ_FUNC = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_longlong)
GET_FUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
SEEK_FUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_longlong, ctypes.c_int)
TELL_FUNC = ctypes.CFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p)
EOF_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
BAD_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLEAR_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
WRITE_FUNC = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_char), ctypes.c_longlong)
PUT_FUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int)

PrecompPtr = ctypes.c_void_p

# 导出函数配置
lib.PrecompCreate.restype = PrecompPtr
lib.PrecompDestroy.argtypes = [PrecompPtr]

# 获取 Context 的接口
lib.PrecompGetRecursionContext.argtypes = [PrecompPtr]
lib.PrecompGetRecursionContext.restype = ctypes.POINTER(CRecursionContext)

lib.PrecompSetGenericInputStream.argtypes = [
    PrecompPtr, ctypes.c_char_p, ctypes.c_void_p,
    READ_FUNC, GET_FUNC, SEEK_FUNC, TELL_FUNC, EOF_FUNC, BAD_FUNC, CLEAR_FUNC
]

lib.PrecompSetGenericOutputStream.argtypes = [
    PrecompPtr, ctypes.c_char_p, ctypes.c_void_p,
    WRITE_FUNC, PUT_FUNC, SEEK_FUNC, TELL_FUNC, EOF_FUNC, BAD_FUNC, CLEAR_FUNC
]

lib.PrecompPrecompress.argtypes = [PrecompPtr]
lib.PrecompPrecompress.restype = ctypes.c_int
lib.PrecompRecompress.argtypes = [PrecompPtr]
lib.PrecompRecompress.restype = ctypes.c_int

# ================= 3. StreamState 类 (修复 EOF 逻辑) =================
class StreamState:
    def __init__(self, f_obj):
        self.f = f_obj
        self.at_eof = False
        # 尝试获取大小
        try:
            self.size = os.fstat(f_obj.fileno()).st_size
        except:
            self.size = 0

    def read(self, backing, buf_ptr, size):
        # 如果之前已经标记 EOF，直接返回 0
        if self.at_eof: return 0
        
        data = self.f.read(size)
        read_len = len(data)
        
        if read_len == 0:
            self.at_eof = True
        elif read_len < size:
            # 读到的比请求的少，说明到了末尾，下次调用就是 EOF
            # 注意：有些流可能只是暂时没数据，但对于文件来说通常意味着 EOF
            pass 
            
        if read_len > 0:
            ctypes.memmove(buf_ptr, data, read_len)
        return read_len

    def get(self, backing):
        if self.at_eof: return -1
        b = self.f.read(1)
        if not b:
            self.at_eof = True
            return -1
        return ord(b)

    def seek(self, backing, offset, origin):
        self.f.seek(offset, origin)
        self.at_eof = False # seek 后重置 EOF
        return 0

    def tell(self, backing):
        return self.f.tell()

    def eof(self, backing):
        return self.at_eof

    def bad(self, backing):
        return False

    def clear(self, backing):
        self.at_eof = False

    def write(self, backing, buf_ptr, size):
        data = ctypes.string_at(buf_ptr, size)
        self.f.write(data)
        return size

    def put(self, backing, char_code):
        self.f.write(bytes([char_code & 0xFF]))
        return char_code

def create_callbacks(stream_state):
    return {
        "read": READ_FUNC(stream_state.read),
        "get": GET_FUNC(stream_state.get),
        "seek": SEEK_FUNC(stream_state.seek),
        "tell": TELL_FUNC(stream_state.tell),
        "eof": EOF_FUNC(stream_state.eof),
        "bad": BAD_FUNC(stream_state.bad),
        "clear": CLEAR_FUNC(stream_state.clear),
        "write": WRITE_FUNC(stream_state.write),
        "put": PUT_FUNC(stream_state.put)
    }

# ================= 4. 任务逻辑 (新增设置长度) =================
def run_precomp_task(input_path, output_path, mode='precompress'):
    print(f"--- 执行 {mode}: {input_path} -> {output_path} ---")
    
    mgr = lib.PrecompCreate()
    if not mgr: return False

    f_in = open(input_path, "rb")
    f_out = open(output_path, "wb")
    
    # 获取文件真实大小
    input_size = os.path.getsize(input_path)

    state_in = StreamState(f_in)
    state_out = StreamState(f_out)
    cbs_in = create_callbacks(state_in)
    cbs_out = create_callbacks(state_out)

    # 保持引用
    keep_alive = (cbs_in, cbs_out)

    try:
        b_in = input_path.encode('utf-8')
        b_out = output_path.encode('utf-8')

        # 1. 设置 Generic I/O
        lib.PrecompSetGenericInputStream(
            mgr, b_in, None,
            cbs_in['read'], cbs_in['get'], cbs_in['seek'], 
            cbs_in['tell'], cbs_in['eof'], cbs_in['bad'], cbs_in['clear']
        )

        lib.PrecompSetGenericOutputStream(
            mgr, b_out, None,
            cbs_out['write'], cbs_out['put'], cbs_out['seek'], 
            cbs_out['tell'], cbs_out['eof'], cbs_out['bad'], cbs_out['clear']
        )

        # ================= 核心修复点 =================
        # 2. 获取上下文并手动设置 fin_length
        # 如果不设置，Precomp 默认长度为 0，循环一次都不执行，只写入 16 字节头部
        context_ptr = lib.PrecompGetRecursionContext(mgr)
        if context_ptr:
            context_ptr.contents.fin_length = input_size
            print(f"已设置 Context.fin_length = {input_size}")
        else:
            print("警告: 无法获取 RecursionContext")
        # ============================================

        res = -1
        if mode == 'precompress':
            res = lib.PrecompPrecompress(mgr)
        else:
            res = lib.PrecompRecompress(mgr)

        # 正常结束 (Code 0 或 2)
        if res == 0 or res == 2:
            print(f">> 成功 (Code {res})")
            return True
        else:
            print(f">> 失败 (Code {res})")
            return False

    finally:
        lib.PrecompDestroy(mgr)
        f_in.close()
        f_out.close()

if __name__ == "__main__":
    test_file = "test.tar"
    # 确保有一个测试文件
    if not os.path.exists(test_file):
        with open(test_file, "wb") as f:
            f.write(b"X" * 30720) # 30KB dummy data

    # 阶段 1
    if run_precomp_task(test_file, "test.pcf", mode="precompress"):
        pcf_size = os.path.getsize("test.pcf")
        print(f"PCF 文件大小: {pcf_size} bytes (应 > 16 bytes)")
        
        # 只有文件里有数据才还原
        if pcf_size > 16:
            # 阶段 2
            if run_precomp_task("test.pcf", "test_restored.tar", mode="recompress"):
                orig_size = os.path.getsize(test_file)
                restored_size = os.path.getsize("test_restored.tar")
                print(f"验证: {orig_size} vs {restored_size}")
                if orig_size == restored_size:
                    print(">> 完美匹配！")
                else:
                    print(">> 大小仍不匹配！")
        else:
            print("预压缩生成的 PCF 文件只有头部，可能是 fin_length 设置失败。")
