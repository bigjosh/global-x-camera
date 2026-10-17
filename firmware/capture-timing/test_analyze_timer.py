import copy
import unittest
from analyze_timer import analyze


class CaptureIntegrityTest(unittest.TestCase):
    def test_overcapture_cannot_qualify_even_with_plausible_timestamps(self):
        w=[0]*224
        w[:6]=[0x54354943,0,300000000,400000000,0x33330000,0x00100000]
        w[13:24]=[2,2,0,1,1,1,1,11,0,0,0xFFFFFFFF]
        w[24]=2
        w[26:32]=[0,0,4,160000000,120000000,160000004]
        # A perfectly plausible10ms pulse with a1.0..1.1us PE0 delay.
        w[32:44]=[50,300300,300330,2,300000,0,300,330,400500,1,3,15]
        w[44:56]=[51,3300300,3300330,2,3300000,0,300,330,4400500,0,5,15]
        result=dict(timer_status_words=w,completed=True,frames=1,
                    events=[dict(id=25,cycles=0),dict(id=3,cycles=800000),dict(id=50,cycles=1200400),
                            dict(id=26,cycles=1210000),dict(id=51,cycles=5200400),dict(id=29,cycles=5300000),
                            dict(id=30,cycles=9600000),dict(id=31,cycles=9601600),dict(id=40,cycles=160000000)])
        # Offset DWT records consistently; TIM5 is independently zero-based.
        w[40]+=800000;w[52]+=800000
        for event in result['events']:event['core_hz']=400000000
        stamps=[0,0.002,0.00300105,0.003025,0.01300105,0.01325,0.024,0.024004,0.4]
        timing=dict(matched=True,mode='cold',events=[dict(id=e['id'],time_s=s,after_nrst_us=s*1e6)
                    for e,s in zip(result['events'],stamps)])
        self.assertTrue(analyze(result,timing)['valid'])
        # Same hardware-cycle counts with a slower oscillator must be decoded
        # through independent non-strobe timing, not rejected as a bad pulse.
        drift=copy.deepcopy(timing)
        for event in drift['events']:
            for key in ('time_s','after_nrst_us'):
                if key in event:event[key]*=1.008
        calibrated=analyze(result,drift)
        self.assertTrue(calibrated['valid'])
        self.assertAlmostEqual(calibrated['measured_core_hz'],400000000/1.008)
        self.assertAlmostEqual(calibrated['pulses'][0]['hardware_width_us'],10080)
        broken=copy.deepcopy(result)
        broken['timer_status_words'][35]|=0x200
        with self.assertRaisesRegex(ValueError,'overwritten capture'):
            analyze(broken,timing)


if __name__=='__main__':unittest.main()
