# Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from operator import __add__, __mul__, __sub__, __truediv__

import numpy as np

import paddle
from paddle import sparse

op_list = [__add__, __sub__, __mul__, __truediv__]


def get_actual_res(x, y, op):
    if op == __add__:
        res = paddle.sparse.add(x, y)
    elif op == __sub__:
        res = paddle.sparse.subtract(x, y)
    elif op == __mul__:
        res = paddle.sparse.multiply(x, y)
    elif op == __truediv__:
        res = paddle.sparse.divide(x, y)
    else:
        raise ValueError("unsupported op")
    return res


def mask_to_zero(x, mask):
    x[mask == 0] = 0
    return x


class TestSparseElementWiseAPI(unittest.TestCase):
    """
    test paddle.sparse.add, subtract, multiply, divide
    """

    def setUp(self):
        np.random.seed(2022)
        self.op_list = op_list
        self.csr_shape = [8, 8]
        self.coo_shape = [4, 8, 3, 5]
        self.support_dtypes = ['float32', 'float64', 'int32', 'int64']

    def func_test_csr(self, op):
        for dtype in self.support_dtypes:
            x = np.random.randint(-255, 255, size=self.csr_shape)
            y = np.random.randint(-255, 255, size=self.csr_shape)
            mask_x = x / x
            mask_y = y / y
            mask_x[mask_x != 1] = 0
            mask_y[mask_y != 1] = 0
            x = x.astype(dtype)
            y = y.astype(dtype)

            dense_x = paddle.to_tensor(x, dtype=dtype, stop_gradient=False)
            dense_y = paddle.to_tensor(y, dtype=dtype, stop_gradient=False)

            s_dense_x = paddle.to_tensor(x, dtype=dtype, stop_gradient=False)
            s_dense_y = paddle.to_tensor(y, dtype=dtype, stop_gradient=False)
            csr_x = s_dense_x.to_sparse_csr()
            csr_y = s_dense_y.to_sparse_csr()

            actual_res = get_actual_res(csr_x, csr_y, op)
            actual_res.backward()

            expect_res = op(dense_x, dense_y)
            expect_res.backward()

            np.testing.assert_allclose(
                expect_res.numpy(),
                actual_res.to_dense().numpy(),
                rtol=1e-05,
                equal_nan=True,
            )
            if not (op == __truediv__ and dtype in ['int32', 'int64']):
                np.testing.assert_allclose(
                    mask_to_zero(dense_x.grad.numpy(), mask_x),
                    csr_x.grad.to_dense().numpy(),
                    rtol=1e-05,
                    equal_nan=True,
                )
                np.testing.assert_allclose(
                    mask_to_zero(dense_y.grad.numpy(), mask_y),
                    csr_y.grad.to_dense().numpy(),
                    rtol=1e-05,
                    equal_nan=True,
                )

    def func_test_coo(self, op):
        for sparse_dim in range(len(self.coo_shape) - 1, len(self.coo_shape)):
            for dtype in self.support_dtypes:
                x = np.random.randint(-255, 255, size=self.coo_shape).astype(
                    dtype
                )
                y = np.random.randint(-255, 255, size=self.coo_shape).astype(
                    dtype
                )

                dense_x = paddle.to_tensor(x, dtype=dtype, stop_gradient=False)
                dense_y = paddle.to_tensor(y, dtype=dtype, stop_gradient=False)

                s_dense_x = paddle.to_tensor(
                    x, dtype=dtype, stop_gradient=False
                )
                s_dense_y = paddle.to_tensor(
                    y, dtype=dtype, stop_gradient=False
                )
                coo_x = s_dense_x.to_sparse_coo(sparse_dim)
                coo_x.retain_grads()
                coo_y = s_dense_y.to_sparse_coo(sparse_dim)
                coo_y.retain_grads()

                actual_res = get_actual_res(coo_x, coo_y, op)
                actual_res.backward(actual_res)

                expect_res = op(dense_x, dense_y)
                expect_res.backward(expect_res)

                np.testing.assert_allclose(
                    expect_res.numpy(),
                    actual_res.to_dense().numpy(),
                    rtol=1e-05,
                    equal_nan=True,
                )
                np.testing.assert_allclose(coo_x.shape, coo_x.grad.shape)
                np.testing.assert_allclose(
                    dense_x.grad.numpy(),
                    coo_x.grad.to_dense().numpy(),
                    rtol=1e-05,
                    equal_nan=True,
                )
                np.testing.assert_allclose(coo_y.shape, coo_y.grad.shape)
                np.testing.assert_allclose(
                    dense_y.grad.numpy(),
                    coo_y.grad.to_dense().numpy(),
                    rtol=1e-05,
                    equal_nan=True,
                )

    def test_support_dtypes_csr(self):
        paddle.device.set_device('cpu')
        if paddle.device.get_device() == "cpu":
            for op in op_list:
                self.func_test_csr(op)

    def test_support_dtypes_coo(self):
        paddle.device.set_device('cpu')
        if paddle.device.get_device() == "cpu":
            for op in op_list:
                self.func_test_coo(op)

    def test_add_same_indices(self):
        indices_data = [[0, 1], [0, 3]]
        values1_data = [[1.0], [2.0]]
        values2_data = [[1.0], [2.0]]
        shape = [2, 4, 2]

        sp_a = sparse.sparse_coo_tensor(
            indices_data, values1_data, shape, stop_gradient=False
        )
        sp_a.retain_grads()

        sp_b = sparse.sparse_coo_tensor(
            indices_data, values2_data, shape, stop_gradient=False
        )
        sp_b.retain_grads()

        values1 = paddle.to_tensor(values1_data, stop_gradient=False)
        values2 = paddle.to_tensor(values2_data, stop_gradient=False)

        # c.values() = a.values() + b.values()
        sp_c = sparse.add(sp_a, sp_b)
        sp_c.backward()
        ref_c = values1 + values2
        ref_c.backward()
        np.testing.assert_allclose(sp_c.values().numpy(), ref_c.numpy())
        np.testing.assert_allclose(
            sp_a.grad.values().numpy(), values1.grad.numpy()
        )
        np.testing.assert_allclose(
            sp_b.grad.values().numpy(), values2.grad.numpy()
        )

    def test_add_bias(self):
        indices_data = [[0, 1], [0, 3]]
        values_data = [[1.0, 1.0], [2.0, 2.0]]
        shape = [2, 4, 2]

        sp_a = sparse.sparse_coo_tensor(
            indices_data, values_data, shape, stop_gradient=False
        )
        sp_a.retain_grads()

        bias_values = [1.0, 2.0]

        values1 = paddle.to_tensor(values_data, stop_gradient=False)
        values2 = paddle.to_tensor(bias_values, stop_gradient=False)
        values3 = paddle.to_tensor(bias_values, stop_gradient=False)

        # c.values() = a.values() + b
        sp_c = sparse.add(sp_a, values2)
        sp_c.backward()
        ref_c = values1 + values3
        ref_c.backward()
        np.testing.assert_allclose(sp_c.values().numpy(), ref_c.numpy())
        np.testing.assert_allclose(
            sp_a.grad.values().numpy(), values1.grad.numpy()
        )
        np.testing.assert_allclose(values2.grad.numpy(), values3.grad.numpy())

    def test_add_bias_cast(self):
        paddle.device.set_device('gpu')
        indices_data = [[0, 1], [0, 3]]
        values_data = [[1.0, 1.0], [2.0, 2.0]]
        shape = [2, 4, 2]

        sp_a = sparse.sparse_coo_tensor(
            indices_data, values_data, shape, dtype="float16", stop_gradient=False, 
        )
        sp_a.retain_grads()

        bias_values = [1.0, 2.0]

        values1 = paddle.to_tensor(values_data, stop_gradient=False)
        values2 = paddle.to_tensor(bias_values, stop_gradient=False)
        values3 = paddle.to_tensor(bias_values, stop_gradient=False)

        # c.values() = a.values() + b
        print(values2.is_sparse())
        print(values2.dtype)
        sp_c = sparse.add(sp_a, values2)
        ref_c = values1 + values3
        np.testing.assert_allclose(sp_c.values().numpy(), ref_c.numpy())


if __name__ == "__main__":
    paddle.device.set_device('cpu')
    unittest.main()
