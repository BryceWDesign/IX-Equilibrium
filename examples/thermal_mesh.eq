system ThermalMesh {
    tick 50 ms;
    sensor a : K fresh 150 ms uncertainty 0.2 K;
    sensor b : K fresh 150 ms uncertainty 0.2 K;
    sensor c : K fresh 150 ms uncertainty 0.2 K;
    input consent : bool fresh 100 ms;
    mesh temperature : K = quorum(a, b, c) tolerance 2 K require 2;
    param power : scalar = 0.1 within [0, 1] rate 0.05;
    actuator heater : scalar range [0, 1] safe 0 slew 1 Hz;
    capability command heater;
    invariant upper_limit : temperature < 315 K;
    state waiting initial { when consent -> regulate; }
    state regulate {
        require consent;
        adapt power = clamp((310 K - temperature) / 10 K, 0, 1);
        command heater = power;
        after 500 ms -> finished;
    }
    state finished terminal { }
    state stopped terminal { }
    on fault -> stopped;
}
