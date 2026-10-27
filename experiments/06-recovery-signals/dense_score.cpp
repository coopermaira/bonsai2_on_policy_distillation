#include "llama.h"
#include "ggml-backend.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void decode(llama_context * ctx, std::vector<llama_token> & tokens) {
    for (size_t i = 0; i < tokens.size(); i += 1024) {
        int n = int(std::min<size_t>(1024, tokens.size()-i));
        if (llama_decode(ctx, llama_batch_get_one(tokens.data()+i, n)) != 0) {
            throw std::runtime_error("decode failed");
        }
    }
}

static std::vector<double> log_probs(llama_context * ctx, int n) {
    const float * logits = llama_get_logits_ith(ctx, -1);
    if (!logits) throw std::runtime_error("missing logits");
    double top = *std::max_element(logits, logits+n);
    double mass = 0;
    for (int j = 0; j < n; ++j) mass += std::exp(double(logits[j])-top);
    double normalizer = top + std::log(mass);
    if (!std::isfinite(normalizer)) throw std::runtime_error("nonfinite logits");
    std::vector<double> result(n);
    for (int j = 0; j < n; ++j) result[j] = logits[j]-normalizer;
    return result;
}

int main(int argc, char ** argv) {
    if (argc != 4) {
        std::cerr << "usage: dense_score teacher.gguf student.gguf cases.tokens\n";
        return 2;
    }
    try {
        ggml_backend_load_all();
        llama_backend_init();
        auto mp = llama_model_default_params();
        mp.n_gpu_layers = 999;
        auto * teacher = llama_model_load_from_file(argv[1], mp);
        auto * student = llama_model_load_from_file(argv[2], mp);
        if (!teacher || !student) throw std::runtime_error("model load failed");
        int vocab = llama_vocab_n_tokens(llama_model_get_vocab(teacher));
        if (vocab != llama_vocab_n_tokens(llama_model_get_vocab(student))) throw std::runtime_error("vocab size mismatch");
        auto cp = llama_context_default_params();
        cp.n_ctx = 49152;
        cp.n_batch = 1024;
        cp.n_ubatch = 512;
        cp.n_threads = 8;
        cp.n_threads_batch = 8;
        cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
        auto * tc = llama_init_from_model(teacher, cp);
        auto * sc = llama_init_from_model(student, cp);
        if (!tc || !sc) throw std::runtime_error("context creation failed");
        std::ifstream input(argv[3]);
        if (!input) throw std::runtime_error("cannot read cases");
        std::string id;
        int prefix_size, target_size;
        std::cout << std::setprecision(12);
        while (input >> id >> prefix_size >> target_size) {
            if (prefix_size < 1 || target_size < 1 || prefix_size+target_size > 49152) throw std::runtime_error("invalid case length");
            std::vector<llama_token> prefix(prefix_size), target(target_size);
            for (auto & token : prefix) if (!(input >> token) || token < 0 || token >= vocab) throw std::runtime_error("invalid prefix token");
            for (auto & token : target) if (!(input >> token) || token < 0 || token >= vocab) throw std::runtime_error("invalid target token");
            llama_memory_clear(llama_get_memory(tc), true);
            llama_memory_clear(llama_get_memory(sc), true);
            decode(tc, prefix);
            decode(sc, prefix);
            for (int i = 0; i < target_size; ++i) {
                auto lp = log_probs(tc, vocab);
                auto lq = log_probs(sc, vocab);
                double forward = 0, reverse = 0, js = 0;
                for (int j = 0; j < vocab; ++j) {
                    double p = std::exp(lp[j]), q = std::exp(lq[j]);
                    double m = .5*(p+q);
                    if (p > 0) { forward += p*(lp[j]-lq[j]); js += .5*p*(lp[j]-std::log(m)); }
                    if (q > 0) { reverse += q*(lq[j]-lp[j]); js += .5*q*(lq[j]-std::log(m)); }
                }
                std::cout << "{\"id\":\"" << id << "\",\"offset\":" << i
                          << ",\"position\":" << prefix_size+i << ",\"token\":" << target[i]
                          << ",\"kl_teacher_student\":" << forward << ",\"kl_student_teacher\":" << reverse
                          << ",\"js\":" << js << ",\"teacher_logprob\":" << lp[target[i]]
                          << ",\"teacher_top1\":" << std::distance(lp.begin(), std::max_element(lp.begin(), lp.end()))
                          << ",\"student_top1\":" << std::distance(lq.begin(), std::max_element(lq.begin(), lq.end()))
                          << ",\"student_logprob\":" << lq[target[i]] << "}" << std::endl;
                std::vector<llama_token> one{target[i]};
                decode(tc, one);
                decode(sc, one);
            }
        }
        llama_free(tc); llama_free(sc);
        llama_model_free(teacher); llama_model_free(student);
        llama_backend_free();
    } catch (const std::exception & e) {
        std::cerr << e.what() << std::endl;
        return 1;
    }
    return 0;
}
