# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
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
# ==============================================================================
"""The Bernoulli distribution class."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow.contrib.distributions.python.ops import distribution
from tensorflow.contrib.distributions.python.ops import distribution_util
from tensorflow.contrib.distributions.python.ops import kullback_leibler
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import ops
from tensorflow.python.framework import tensor_shape
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops
from tensorflow.python.ops import nn
from tensorflow.python.ops import random_ops


class Bernoulli(distribution.Distribution):
  """Bernoulli distribution.

  The Bernoulli distribution is parameterized by p, the probability of a
  positive event.
  """

  def __init__(self,
               logits=None,
               p=None,
               dtype=dtypes.int32,
               validate_args=False,
               allow_nan_stats=True,
               name="Bernoulli"):
    """Construct Bernoulli distributions.

    Args:
      logits: An N-D `Tensor` representing the log-odds
        of a positive event. Each entry in the `Tensor` parametrizes
        an independent Bernoulli distribution where the probability of an event
        is sigmoid(logits).
      p: An N-D `Tensor` representing the probability of a positive
          event. Each entry in the `Tensor` parameterizes an independent
          Bernoulli distribution.
      dtype: dtype for samples.
      validate_args: `Boolean`, default `False`.  Whether to validate that
        `0 <= p <= 1`. If `validate_args` is `False`, and the inputs are
        invalid, methods like `log_pmf` may return `NaN` values.
      allow_nan_stats: `Boolean`, default `True`.  If `False`, raise an
        exception if a statistic (e.g. mean/mode/etc...) is undefined for any
        batch member.  If `True`, batch members with valid parameters leading to
        undefined statistics will return NaN for this statistic.
      name: A name for this distribution.

    Raises:
      ValueError: If p and logits are passed, or if neither are passed.
    """
    with ops.name_scope(name) as ns:
      self._logits, self._p = distribution_util.get_logits_and_prob(
          logits=logits, p=p, validate_args=validate_args)
      with ops.name_scope("q"):
        self._q = 1. - self._p
      super(Bernoulli, self).__init__(
          dtype=dtype,
          parameters={"p": self._p, "q": self._q, "logits": self._logits},
          is_continuous=False,
          is_reparameterized=False,
          validate_args=validate_args,
          allow_nan_stats=allow_nan_stats,
          name=ns)

  @staticmethod
  def _param_shapes(sample_shape):
    return {"logits": ops.convert_to_tensor(sample_shape, dtype=dtypes.int32)}

  @property
  def logits(self):
    return self._logits

  @property
  def p(self):
    return self._p

  @property
  def q(self):
    """1-p."""
    return self._q

  def _batch_shape(self):
    return array_ops.shape(self._logits)

  def _get_batch_shape(self):
    return self._logits.get_shape()

  def _event_shape(self):
    return array_ops.constant([], dtype=dtypes.int32)

  def _get_event_shape(self):
    return tensor_shape.scalar()

  def _sample_n(self, n, seed=None):
    new_shape = array_ops.concat(0, ([n], self.batch_shape()))
    uniform = random_ops.random_uniform(
        new_shape, seed=seed, dtype=self.p.dtype)
    sample = math_ops.less(uniform, self.p)
    return math_ops.cast(sample, self.dtype)

  def _log_prob(self, event):
    # TODO(jaana): The current sigmoid_cross_entropy_with_logits has
    # inconsistent  behavior for logits = inf/-inf.
    event = ops.convert_to_tensor(event, name="event")
    event = math_ops.cast(event, self.logits.dtype)
    logits = self.logits
    # sigmoid_cross_entropy_with_logits doesn't broadcast shape,
    # so we do this here.
    # TODO(b/30637701): Check dynamic shape, and don't broadcast if the
    # dynamic shapes are the same.
    if (not event.get_shape().is_fully_defined() or
        not logits.get_shape().is_fully_defined() or
        event.get_shape() != logits.get_shape()):
      logits = array_ops.ones_like(event) * logits
      event = array_ops.ones_like(logits) * event
    return -nn.sigmoid_cross_entropy_with_logits(logits, event)

  def _prob(self, event):
    return math_ops.exp(self._log_prob(event))

  def _entropy(self):
    # TODO(b/31086883): use tf.nn.softplus; fix inconsistent behavior between
    # cpu and gpu at -inf/inf.
    return (-self.logits * (math_ops.sigmoid(self.logits) - 1) +
            math_ops.log(1. + math_ops.exp(-self.logits)))

  def _mean(self):
    return array_ops.identity(self.p)

  def _variance(self):
    return self.q * self.p

  def _std(self):
    return math_ops.sqrt(self._variance())

  def _mode(self):
    return math_ops.cast(self.p > self.q, self.dtype)


distribution_util.append_class_fun_doc(Bernoulli.mode, doc_str="""

  Specific notes:
    1 if p > 1-p. 0 otherwise.
""")


class BernoulliWithSigmoidP(Bernoulli):
  """Bernoulli with `p = sigmoid(p)`."""

  def __init__(self,
               p=None,
               dtype=dtypes.int32,
               validate_args=False,
               allow_nan_stats=True,
               name="BernoulliWithSigmoidP"):
    with ops.name_scope(name) as ns:
      super(BernoulliWithSigmoidP, self).__init__(
          p=nn.sigmoid(p),
          dtype=dtype,
          validate_args=validate_args,
          allow_nan_stats=allow_nan_stats,
          name=ns)


@kullback_leibler.RegisterKL(Bernoulli, Bernoulli)
def _kl_bernoulli_bernoulli(a, b, name=None):
  """Calculate the batched KL divergence KL(a || b) with a and b Bernoulli.

  Args:
    a: instance of a Bernoulli distribution object.
    b: instance of a Bernoulli distribution object.
    name: (optional) Name to use for created operations.
      default is "kl_bernoulli_bernoulli".

  Returns:
    Batchwise KL(a || b)
  """
  with ops.name_scope(name, "kl_bernoulli_bernoulli", [a.logits, b.logits]):
    return (math_ops.sigmoid(a.logits) * (-nn.softplus(-a.logits) +
                                          nn.softplus(-b.logits)) +
            math_ops.sigmoid(-a.logits) * (-nn.softplus(a.logits) +
                                           nn.softplus(b.logits)))
