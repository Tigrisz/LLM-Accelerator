#pragma once
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <cstdint>
struct VectorCase {
    int n, k, padded;
    std::vector<int> weights, activations;
    std::vector<int32_t> expected;
    explicit VectorCase(const std::string& path) {
        std::ifstream file(path);
        if (!(file >> n >> k >> padded) || n<1 || k<1 || padded%128 || padded<k)
            throw std::runtime_error("invalid vector header: " + path);
        weights.resize(n*padded/2); activations.resize(padded); expected.resize(n*(padded/128));
        for(auto& v:weights) if(!(file>>v) || v<0 || v>255) throw std::runtime_error("weight file truncated/range");
        for(auto& v:activations) if(!(file>>v) || v<0 || v>255) throw std::runtime_error("activation file truncated/range");
        for(auto& v:expected) if(!(file>>v)) throw std::runtime_error("golden file truncated");
    }
    int w(int row,int col) const {
        int nibble=(weights[row*padded/2+col/2] >> (4*(col%2))) & 15;
        return nibble>=8?nibble-16:nibble;
    }
    int x(int col) const { return activations[col]>=128?activations[col]-256:activations[col]; }
};
