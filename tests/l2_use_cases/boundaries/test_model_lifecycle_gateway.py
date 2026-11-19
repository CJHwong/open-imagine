from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway


class Model(ModelLifecycleGateway):
    def __init__(self):
        self.loads = 0

    def load(self):
        self.loads += 1

    def release(self):
        pass


def test_a_model_that_fetches_in_its_load_prepares_by_loading():
    model = Model()

    model.prepare()

    assert model.loads == 1
