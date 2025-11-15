import sys
import os

# 将编译输出目录加入路径，以便导入模块
sys.path.append("./build/Release") # Windows
sys.path.append("./build")         # Linux

import precomp_py

def run_test():
    # 1. 创建实例
    mgr = precomp_py.Precomp()
    
    # 2. 配置开关 (示例)
    mgr.switches.min_ident_size = 4
    mgr.switches.intense_mode = False
    
    input_file = "test.tar"
    pcf_file = "test.pcf"
    restored_file = "test_restored.tar"
    
    # 创建测试文件
    if not os.path.exists(input_file):
        with open(input_file, "wb") as f:
            f.write(b"A" * 1024 * 100) # 100KB 数据

    print(f"--- 预压缩: {input_file} -> {pcf_file} ---")
    try:
        # 直接传文件名，C++ 内部自动处理流和文件大小！
        res = mgr.precompress_file(input_file, pcf_file)
        print(f"结果代码: {res}") # 0=成功, 2=无压缩内容(正常)
        
        print(f"PCF 大小: {os.path.getsize(pcf_file)} bytes")

        print(f"\n--- 还原: {pcf_file} -> {restored_file} ---")
        # 还原时，建议创建新的实例以重置状态
        mgr_restore = precomp_py.Precomp()
        res2 = mgr_restore.recompress_file(pcf_file, restored_file)
        print(f"结果代码: {res2}")
        
        orig_size = os.path.getsize(input_file)
        rest_size = os.path.getsize(restored_file)
        print(f"验证: 原文件 {orig_size} vs 还原 {rest_size}")
        
        if orig_size == rest_size:
            print("SUCCESS: 文件大小一致")
        else:
            print("FAIL: 文件大小不一致")

    except RuntimeError as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    run_test()
