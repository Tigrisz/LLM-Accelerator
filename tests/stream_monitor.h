#pragma once
#include <stdexcept>
#include <string>

// Sample immediately before each rising edge. A blocked producer must retain
// valid AND its complete payload on the next sample, even if ready then rises.
template<class Payload> class StreamMonitor {
    bool pending=false;
    Payload previous{};
    std::string name;
public:
    explicit StreamMonitor(const std::string& channel): name(channel) {}
    void reset() { pending=false; }
    void sample(bool valid, bool ready, const Payload& payload) {
        if(pending && (!valid || payload!=previous))
            throw std::runtime_error(name + ": payload/valid changed after a blocked cycle");
        pending=valid && !ready;
        if(pending) previous=payload;
    }
};

// Legal-stimulus checker; no new hardware error port or invalid-input promise.
class GroupMonitor {
    unsigned position=0, row=0, group=0, beats;
public:
    explicit GroupMonitor(unsigned lanes): beats(128/lanes) {
        if(lanes!=16 && lanes!=32) throw std::runtime_error("unsupported lanes");
    }
    void reset() { position=0; }
    void sample(bool accepted,bool first,bool last,unsigned r,unsigned g) {
        if(!accepted) return;
        if(first!=(position==0) || last!=(position==beats-1))
            throw std::runtime_error("group: misplaced first/last on accepted beat");
        if(position==0) { row=r; group=g; }
        if(r!=row || g!=group) throw std::runtime_error("group: label changed within group");
        position=(position+1)%beats;
    }
};
