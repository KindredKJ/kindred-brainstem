# DCML numerical policy training

The trainable component is a four-feature, per-strategy linear contextual policy optimized locally with seeded stochastic gradient updates against verified rewards. Runs record data IDs, split IDs, seed, learning rate, epochs, pre/post parameter hashes, and a candidate checkpoint. Candidate parameters cannot affect selection until canary success and a signed promotion.

This is real numerical DCML policy training. It is not foundation-model or adapter-weight training.
