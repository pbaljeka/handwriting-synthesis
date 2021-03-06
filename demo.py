import os

import numpy as np
import svgwrite

import drawing
import lyrics
from rnn import rnn


def sample(nn, lines, biases=None, styles=None):
    num_samples = len(lines)
    max_tsteps = 40*max([len(i) for i in lines])
    biases = biases or [0.5]*num_samples

    x_prime = np.zeros([num_samples, 1200, 3])
    x_prime_len = np.zeros([num_samples])
    chars = np.zeros([num_samples, 100])
    chars_len = np.zeros([num_samples])

    if styles is not None:
        for i, (cs, style) in enumerate(zip(lines, styles)):
            x_p = np.load('styles/style-{}-strokes.npy'.format(style))
            c_p = np.load('styles/style-{}-chars.npy'.format(style))

            c_p = str(c_p) + " " + cs
            c_p = drawing.encode_ascii(c_p)
            c_p = np.array(c_p)

            x_prime[i, :len(x_p), :] = x_p
            x_prime_len[i] = len(x_p)
            chars[i, :len(c_p)] = c_p
            chars_len[i] = len(c_p)

    else:
        for i in range(num_samples):
            encoded = drawing.encode_ascii(lines[i])
            chars[i, :len(encoded)] = encoded
            chars_len[i] = len(encoded)

    [samples] = nn.session.run(
        [nn.sampled_sequence],
        feed_dict={
            nn.prime: styles is not None,
            nn.x_prime: x_prime,
            nn.x_prime_len: x_prime_len,
            nn.num_samples: num_samples,
            nn.sample_tsteps: max_tsteps,
            nn.c: chars,
            nn.c_len: chars_len,
            nn.bias: biases
        }
    )
    samples = [sample[~np.all(sample == 0.0, axis=1)] for sample in samples]
    return samples


def draw(strokes, lines, filename, align=True, denoise=True):
    line_height = 60
    view_width = 1000
    view_height = line_height*(len(strokes) + 1)

    dwg = svgwrite.Drawing(filename=filename)
    dwg.viewbox(width=view_width, height=view_height)
    dwg.add(dwg.rect(insert=(0, 0), size=(view_width, view_height), fill='white'))

    initial_coord = np.array([0, -line_height])
    for offsets, line in zip(strokes, lines):

        if not line:
            initial_coord[1] -= line_height
            continue

        offsets[:, :2] *= 1.5
        strokes = drawing.offsets_to_coords(offsets)
        strokes = drawing.denoise(strokes) if denoise else strokes
        strokes[:, :2] = drawing.align(strokes[:, :2]) if align else strokes

        strokes[:, 1] *= -1
        strokes[:, :2] -= strokes[:, :2].min() + initial_coord
        strokes[:, 0] += (view_width - strokes[:, 0].max()) / 2

        prev_eos = 1.0
        p = "M{},{} ".format(0, 0)
        for x, y, eos in zip(*strokes.T):
            p += '{}{},{} '.format('M' if prev_eos == 1.0 else 'L', x, y)
            prev_eos = eos
        path = svgwrite.path.Path(p)
        path = path.stroke(color="black", width=2, linecap='round').fill("none")
        dwg.add(path)

        initial_coord[1] -= line_height

    dwg.save()

if __name__ == '__main__':
    nn = rnn(
        log_dir='logs',
        checkpoint_dir='checkpoints',
        prediction_dir='predictions',
        learning_rates=[.0001, .00005, .00002],
        batch_sizes=[32, 64, 64],
        patiences=[1500, 1000, 500],
        beta1_decays=[.9, .9, .9],
        validation_batch_size=32,
        optimizer='rms',
        num_training_steps=100000,
        warm_start_init_step=17900,
        regularization_constant=0.0,
        keep_prob=1.0,
        enable_parameter_averaging=False,
        min_steps_to_checkpoint=2000,
        log_interval=20,
        grad_clip=10,
        lstm_size=400,
        output_mixture_components=20,
        attention_mixture_components=10
    )
    nn.restore()

    if not os.path.exists('img'):
        os.makedirs('img')

    # demo number 1 - fixed bias, fixed style
    lines = lyrics.all_star.split("\n")
    biases = [.75 for i in lines]
    styles = [12 for i in lines]
    strokes = sample(nn, lines, biases=biases, styles=styles)
    draw(strokes, lines, filename='img/{}.svg'.format('all_star'))

    # demo number 2 - fixed bias, varying style
    lines = lyrics.downtown.split("\n")
    biases = [.75 for i in lines]
    styles = np.cumsum(np.array([len(i) for i in lines]) == 0).astype(int)
    strokes = sample(nn, lines, biases=biases, styles=styles)
    draw(strokes, lines, filename='img/{}.svg'.format('downtown'))

    # demo number 3 - varying bias, fixed style
    lines = lyrics.give_up.split("\n")
    verse_nums = np.cumsum(np.array([len(i) for i in lines]) == 0)
    biases = [.2*(max(verse_nums) - i) for i in verse_nums]
    styles = [7 for i in lines]
    strokes = sample(nn, lines, biases=biases, styles=styles)
    draw(strokes, lines, filename='img/{}.svg'.format('give_up'))
