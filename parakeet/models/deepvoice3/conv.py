import numpy as np
from paddle.fluid import layers as F
from paddle.fluid.framework import Variable, in_dygraph_mode
from paddle.fluid import core, dygraph_utils
from paddle.fluid.layers import nn, utils
from paddle.fluid.data_feeder import check_variable_and_dtype
from paddle.fluid.param_attr import ParamAttr
from paddle.fluid.layer_helper import LayerHelper
from paddle.fluid.dygraph import layers
from paddle.fluid.initializer import Normal


def _is_list_or_tuple(input):
    return isinstance(input, (list, tuple))


def _zero_padding_in_batch_and_channel(padding, channel_last):
    if channel_last:
        return list(padding[0]) == [0, 0] and list(padding[-1]) == [0, 0]
    else:
        return list(padding[0]) == [0, 0] and list(padding[1]) == [0, 0]


def _exclude_padding_in_batch_and_channel(padding, channel_last):
    padding_ = padding[1:-1] if channel_last else padding[2:]
    padding_ = [elem for pad_a_dim in padding_ for elem in pad_a_dim]
    return padding_


def _update_padding_nd(padding, channel_last, num_dims):
    if isinstance(padding, str):
        padding = padding.upper()
        if padding not in ["SAME", "VALID"]:
            raise ValueError(
                "Unknown padding: '{}'. It can only be 'SAME' or 'VALID'.".
                format(padding))
        if padding == "VALID":
            padding_algorithm = "VALID"
            padding = [0] * num_dims
        else:
            padding_algorithm = "SAME"
            padding = [0] * num_dims
    elif _is_list_or_tuple(padding):
        # for padding like
        # [(pad_before, pad_after), (pad_before, pad_after), ...]
        # padding for batch_dim and channel_dim included
        if len(padding) == 2 + num_dims and _is_list_or_tuple(padding[0]):
            if not _zero_padding_in_batch_and_channel(padding, channel_last):
                raise ValueError(
                    "Non-zero padding({}) in the batch or channel dimensions "
                    "is not supported.".format(padding))
            padding_algorithm = "EXPLICIT"
            padding = _exclude_padding_in_batch_and_channel(padding,
                                                            channel_last)
            if utils._is_symmetric_padding(padding, num_dims):
                padding = padding[0::2]
        # for padding like [pad_before, pad_after, pad_before, pad_after, ...]
        elif len(padding) == 2 * num_dims and isinstance(padding[0], int):
            padding_algorithm = "EXPLICIT"
            padding = utils.convert_to_list(padding, 2 * num_dims, 'padding')
            if utils._is_symmetric_padding(padding, num_dims):
                padding = padding[0::2]
        # for padding like [pad_d1, pad_d2, ...]
        elif len(padding) == num_dims and isinstance(padding[0], int):
            padding_algorithm = "EXPLICIT"
            padding = utils.convert_to_list(padding, num_dims, 'padding')
        else:
            raise ValueError("In valid padding: {}".format(padding))
    # for integer padding
    else:
        padding_algorithm = "EXPLICIT"
        padding = utils.convert_to_list(padding, num_dims, 'padding')
    return padding, padding_algorithm

def _get_default_param_initializer(num_channels, filter_size):
    filter_elem_num = num_channels * np.prod(filter_size)
    std = (2.0 / filter_elem_num)**0.5
    return Normal(0.0, std, 0)

def conv1d(input,
           weight,
           bias=None,
           padding=0,
           stride=1,
           dilation=1,
           groups=1,
           use_cudnn=True,
           act=None,
           data_format="NCT",
           name=None):
    # entry checks
    if not isinstance(use_cudnn, bool):
        raise ValueError("Attr(use_cudnn) should be True or False. "
                         "Received Attr(use_cudnn): {}.".format(use_cudnn))
    if data_format not in ["NCT", "NTC"]:
        raise ValueError("Attr(data_format) should be 'NCT' or 'NTC'. "
                         "Received Attr(data_format): {}.".format(data_format))

    channel_last = (data_format == "NTC")
    channel_dim = -1 if channel_last else 1
    num_channels = input.shape[channel_dim]
    num_filters = weight.shape[0]
    if num_channels < 0:
        raise ValueError("The channel dimmention of the input({}) "
                         "should be defined. Received: {}.".format(
                             input.shape, num_channels))
    if num_channels % groups != 0:
        raise ValueError(
            "the channel of input must be divisible by groups,"
            "received: the channel of input is {}, the shape of input is {}"
            ", the groups is {}".format(num_channels, input.shape, groups))
    if num_filters % groups != 0:
        raise ValueError(
            "the number of filters must be divisible by groups,"
            "received: the number of filters is {}, the shape of weight is {}"
            ", the groups is {}".format(num_filters, weight.shape, groups))

    # update attrs
    padding, padding_algorithm = _update_padding_nd(padding, channel_last, 1)
    if len(padding) == 1: # synmmetric padding
        padding = [0,] + padding
    else:
        # len(padding) == 2
        padding = [0, 0] + padding
    stride = [1,] + utils.convert_to_list(stride, 1, 'stride')
    dilation = [1,] + utils.convert_to_list(dilation, 1, 'dilation')
    data_format = "NHWC" if channel_last else "NCHW"

    l_type = "conv2d"

    if (num_channels == groups and num_filters % num_channels == 0 and
            not use_cudnn):
        l_type = 'depthwise_conv2d'
    weight = F.unsqueeze(weight, [2])
    input = F.unsqueeze(input, [1]) if channel_last else F.unsqueeze(input, [2])

    if in_dygraph_mode():
        attrs = ('strides', stride, 'paddings', padding, 'dilations', dilation,
                 'groups', groups, 'use_cudnn', use_cudnn, 'use_mkldnn', False,
                 'fuse_relu_before_depthwise_conv', False, "padding_algorithm",
                 padding_algorithm, "data_format", data_format)
        pre_bias = getattr(core.ops, l_type)(input, weight, *attrs)
        if bias is not None:
            pre_act = nn.elementwise_add(pre_bias, bias, axis=channel_dim)
        else:
            pre_act = pre_bias
        out = dygraph_utils._append_activation_in_dygraph(
            pre_act, act, use_cudnn=use_cudnn)
    else:
        inputs = {'Input': [input], 'Filter': [weight]}
        attrs = {
            'strides': stride,
            'paddings': padding,
            'dilations': dilation,
            'groups': groups,
            'use_cudnn': use_cudnn,
            'use_mkldnn': False,
            'fuse_relu_before_depthwise_conv': False,
            "padding_algorithm": padding_algorithm,
            "data_format": data_format
        }
        check_variable_and_dtype(input, 'input',
                                 ['float16', 'float32', 'float64'], 'conv2d')
        helper = LayerHelper(l_type, **locals())
        dtype = helper.input_dtype()
        pre_bias = helper.create_variable_for_type_inference(dtype)
        outputs = {"Output": [pre_bias]}
        helper.append_op(
            type=l_type, inputs=inputs, outputs=outputs, attrs=attrs)
        if bias is not None:
            pre_act = nn.elementwise_add(pre_bias, bias, axis=channel_dim)
        else:
            pre_act = pre_bias
        out = helper.append_activation(pre_act)
    out = F.squeeze(out, [1]) if channel_last else F.squeeze(out, [2])
    return out

class Conv1D(layers.Layer):
    def __init__(self,
                 num_channels,
                 num_filters,
                 filter_size,
                 padding=0,
                 stride=1,
                 dilation=1,
                 groups=1,
                 param_attr=None,
                 bias_attr=None,
                 use_cudnn=True,
                 act=None,
                 data_format="NCT",
                 dtype='float32'):
        super(Conv1D, self).__init__()
        assert param_attr is not False, "param_attr should not be False here."
        self._num_channels = num_channels
        self._num_filters = num_filters
        self._groups = groups
        if num_channels % groups != 0:
            raise ValueError("num_channels must be divisible by groups.")
        self._act = act
        self._data_format = data_format
        self._dtype = dtype
        if not isinstance(use_cudnn, bool):
            raise ValueError("use_cudnn should be True or False")
        self._use_cudnn = use_cudnn

        self._filter_size = utils.convert_to_list(filter_size, 1, 'filter_size')
        self._stride = utils.convert_to_list(stride, 1, 'stride')
        self._dilation = utils.convert_to_list(dilation, 1, 'dilation')
        channel_last = (data_format == "NTC")
        self._padding = padding  # leave it to F.conv1d

        self._param_attr = param_attr
        self._bias_attr = bias_attr

        num_filter_channels = num_channels // groups
        filter_shape = [self._num_filters, num_filter_channels
                        ] + self._filter_size

        self.weight = self.create_parameter(
            attr=self._param_attr,
            shape=filter_shape,
            dtype=self._dtype,
            default_initializer=_get_default_param_initializer(
                self._num_channels, filter_shape))
        self.bias = self.create_parameter(
            attr=self._bias_attr,
            shape=[self._num_filters],
            dtype=self._dtype,
            is_bias=True)

    def forward(self, input):
        out = conv1d(
            input,
            self.weight,
            bias=self.bias,
            padding=self._padding,
            stride=self._stride,
            dilation=self._dilation,
            groups=self._groups,
            use_cudnn=self._use_cudnn,
            act=self._act,
            data_format=self._data_format)
        return out

