# Parakeet

Parakeet aims to provide a flexible, efficient and state-of-the-art text-to-speech toolkit for the open-source community. It is built on Paddle Fluid dynamic graph, with the support of many influential TTS models proposed by [Baidu Research](http://research.baidu.com) and other academic institutions.  

<div align="center">
  <img src="images/logo.png" width=450 /> <br>
</div>

### Setup

Make sure the library `libsndfile1` installed, e.g., on Ubuntu

```bash
sudo apt-get install libsndfile1
```

### Install PaddlePaddle

See [install](https://www.paddlepaddle.org.cn/install/quick) for more details. This repo requires paddlepaddle's version is above 1.7.

### Install Parakeet

```bash
# git clone this repo first
cd Parakeet
pip install -e .
```

### Install CMUdict for nltk

CMUdict from nltk is used to transform text into phonemes.
```python
import nltk
nltk.download("punkt")
nltk.download("cmudict")
```


## Supported models

- [Deep Voice 3: Scaling Text-to-Speech with Convolutional Sequence Learning](https://arxiv.org/abs/1710.07654)
- [Neural Speech Synthesis with Transformer Network](https://arxiv.org/abs/1809.08895)
- [FastSpeech: Fast, Robust and Controllable Text to Speech](https://arxiv.org/abs/1905.09263).

## Examples

- [Train a deepvoice 3 model with ljspeech dataset](./parakeet/examples/deepvoice3)
- [Train a transformer_tts model with ljspeech dataset](./parakeet/examples/transformer_tts)
- [Train a fastspeech model with ljspeech dataset](./parakeet/examples/fastspeech)
