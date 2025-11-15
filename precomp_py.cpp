#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <fstream>
#include <filesystem>
#include <iostream>

#include "precomp_dll.h" 

namespace py = pybind11;
namespace fs = std::filesystem;

// 辅助函数：执行预压缩
int python_precompress(Precomp& self, const std::string& input_file, const std::string& output_file) {
    auto fin = new std::ifstream(input_file, std::ios::binary);
    auto fout = new std::ofstream(output_file, std::ios::binary);

    if (!fin->is_open() || !fout->is_open()) {
        delete fin;
        delete fout;
        throw std::runtime_error("Failed to open input or output file.");
    }

    auto file_size = fs::file_size(input_file);
    self.get_original_context()->fin_length = file_size;

    self.set_input_stream(fin, true);
    self.set_output_stream(fout, true);

    return PrecompPrecompress(&self);
}

// 辅助函数：执行还原
int python_recompress(Precomp& self, const std::string& input_file, const std::string& output_file) {
    auto fin = new std::ifstream(input_file, std::ios::binary);
    auto fout = new std::ofstream(output_file, std::ios::binary);

    if (!fin->is_open() || !fout->is_open()) {
        delete fin;
        delete fout;
        throw std::runtime_error("Failed to open input or output file.");
    }

    self.get_original_context()->fin_length = fs::file_size(input_file);
    self.set_input_stream(fin, true);
    self.set_output_stream(fout, true);

    return PrecompRecompress(&self);
}

PYBIND11_MODULE(precomp_py, m) {
    m.doc() = "Precomp Neo Python Bindings via pybind11";

    // ==================== 修复点 1 ====================
    // 注册真正的 C++ 类型 'Switches'，而不是基类 'CSwitches'
    // 因为它是 CSwitches 的子类，我们可以直接绑定父类的成员变量
    py::class_<Switches>(m, "Switches")
        .def(py::init<>())
        .def_readwrite("intense_mode", &Switches::intense_mode)
        .def_readwrite("brute_mode", &Switches::brute_mode)
        .def_readwrite("min_ident_size", &Switches::min_ident_size)
        .def_readwrite("use_pdf", &Switches::use_pdf)
        .def_readwrite("use_zip", &Switches::use_zip)
        .def_readwrite("use_jpg", &Switches::use_jpg)
        .def_readwrite("use_png", &Switches::use_png)
        .def_readwrite("use_gif", &Switches::use_gif)
        .def_readwrite("use_base64", &Switches::use_base64)
        .def_readwrite("use_bzip2", &Switches::use_bzip2)
        .def_readwrite("max_recursion_depth", &Switches::max_recursion_depth);

    // 绑定 Precomp 主类
    py::class_<Precomp>(m, "Precomp")
        .def(py::init<>()) 
        // ==================== 修复点 2 ====================
        // 使用 reference_internal 策略。
        // 如果不加这个，Python 会获得 switches 的一份拷贝。
        // 你修改 mgr.switches.min_ident_size = 4 只会修改拷贝，不会影响 mgr 内部的配置。
        .def_readonly("switches", &Precomp::switches, py::return_value_policy::reference_internal)
        
        .def("precompress_file", &python_precompress, 
             py::arg("input_file"), py::arg("output_file"),
             "Precompress a file. Returns 0 on success, 2 if nothing to compress.")
        .def("recompress_file", &python_recompress,
             py::arg("input_file"), py::arg("output_file"),
             "Recompress (restore) a PCF file to original.");

    m.def("set_logging_callback", [](std::function<void(int, std::string)> cb) {
        static auto python_cb = cb;
        PrecompSetLoggingCallback([](PrecompLoggingLevels level, char* msg) {
            if (python_cb) python_cb((int)level, std::string(msg));
        });
    });
}
