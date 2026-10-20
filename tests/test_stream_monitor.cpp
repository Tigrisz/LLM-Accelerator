#include "stream_monitor.h"
#include <array>
#include <functional>
#include <iostream>

int main() {
    unsigned rejected=0;
    auto reject=[&](const std::function<void()>& stimulus) {
        try { stimulus(); } catch(const std::runtime_error&) { ++rejected; return; }
        throw std::runtime_error("monitor failed to reject corrupt stimulus");
    };
    try {
        using Payload=std::array<unsigned,4>;
        Payload p{{1,2,3,4}};
        // Corrupt each payload field on both a blocked and an accepting edge.
        for(unsigned field=0;field<4;field++) for(bool ready:{false,true}) reject([&] {
            StreamMonitor<Payload> m("test"); m.sample(true,false,p);
            auto q=p; ++q[field]; m.sample(true,ready,q);
        });
        reject([&] { StreamMonitor<Payload> m("test"); m.sample(true,false,p); m.sample(false,true,p); });
        StreamMonitor<Payload> m("legal"); m.sample(true,false,p); m.sample(true,true,p);
        auto q=p; ++q[0]; m.sample(true,true,q);
        m.sample(true,false,p); m.reset(); m.sample(false,false,q);
        for(unsigned lanes:{16u,32u}) {
            reject([&] { GroupMonitor g(lanes); g.sample(true,false,false,0,0); });
            reject([&] { GroupMonitor g(lanes); g.sample(true,true,true,0,0); });
            reject([&] { GroupMonitor g(lanes); g.sample(true,true,false,0,0); g.sample(true,true,false,0,0); });
            reject([&] { GroupMonitor g(lanes); g.sample(true,true,false,0,0); g.sample(true,false,false,1,0); });
            reject([&] { GroupMonitor g(lanes); g.sample(true,true,false,0,0); g.sample(true,false,false,0,1); });
            reject([&] { GroupMonitor g(lanes); for(unsigned i=0;i<128/lanes;i++) g.sample(true,i==0,false,0,0); });
            GroupMonitor g(lanes);
            for(unsigned i=0;i<128/lanes;i++) {
                g.sample(false,true,true,999,999); // Invalid payload ignored without handshake.
                g.sample(true,i==0,i==128/lanes-1,3,7);
            }
            g.sample(true,true,false,4,0); g.reset(); g.sample(true,true,false,9,8);
        }
        std::cout<<"PASS MONITORS injected_violations="<<rejected<<" legal_stall_reset=PASS\n";
    } catch(const std::exception& e) { std::cerr<<"FAIL "<<e.what()<<'\n'; return 1; }
}
