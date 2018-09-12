#![feature(never_type, panic_implementation, panic_info_message, const_slice_len, try_from)]
#![no_std]

#[macro_use]
extern crate log;
#[macro_use]
extern crate board_misoc;
extern crate board_artiq;

use core::convert::TryFrom;
use board_misoc::{csr, irq, ident, clock, uart_logger};
use board_artiq::{i2c, spi, si5324, drtioaux};
#[cfg(has_serwb_phy_amc)]
use board_artiq::serwb;
use board_artiq::drtio_routing;
#[cfg(has_hmc830_7043)]
use board_artiq::hmc830_7043;

mod repeater;

fn drtiosat_reset(reset: bool) {
    unsafe {
        csr::drtiosat::reset_write(if reset { 1 } else { 0 });
    }
}

fn drtiosat_reset_phy(reset: bool) {
    unsafe {
        csr::drtiosat::reset_phy_write(if reset { 1 } else { 0 });
    }
}

fn drtiosat_link_rx_up() -> bool {
    unsafe {
        csr::drtiosat::rx_up_read() == 1
    }
}

fn drtiosat_tsc_loaded() -> bool {
    unsafe {
        let tsc_loaded = csr::drtiosat::tsc_loaded_read() == 1;
        if tsc_loaded {
            csr::drtiosat::tsc_loaded_write(1);
        }
        tsc_loaded
    }
}

fn process_aux_packet(_repeaters: &mut [repeater::Repeater],
        _routing_table: &mut drtio_routing::RoutingTable, _rank: &mut u8,
        packet: drtioaux::Packet) -> Result<(), drtioaux::Error<!>> {
    // In the code below, *_chan_sel_write takes an u8 if there are fewer than 256 channels,
    // and u16 otherwise; hence the `as _` conversion.
    match packet {
        drtioaux::Packet::EchoRequest =>
            drtioaux::send_link(0, &drtioaux::Packet::EchoReply),
        drtioaux::Packet::ResetRequest { phy } => {
            info!("resetting RTIO");
            if phy {
                drtiosat_reset_phy(true);
                drtiosat_reset_phy(false);
            } else {
                drtiosat_reset(true);
                drtiosat_reset(false);
            }
            for rep in _repeaters.iter() {
                if let Err(e) = rep.rtio_reset(phy) {
                    error!("failed to issue RTIO reset ({})", e);
                }
            }
            drtioaux::send_link(0, &drtioaux::Packet::ResetAck)
        },

        drtioaux::Packet::RtioErrorRequest => {
            let errors;
            unsafe {
                errors = csr::drtiosat::rtio_error_read();
            }
            if errors & 1 != 0 {
                let channel;
                unsafe {
                    channel = csr::drtiosat::sequence_error_channel_read();
                    csr::drtiosat::rtio_error_write(1);
                }
                drtioaux::send_link(0,
                    &drtioaux::Packet::RtioErrorSequenceErrorReply { channel })
            } else if errors & 2 != 0 {
                let channel;
                unsafe {
                    channel = csr::drtiosat::collision_channel_read();
                    csr::drtiosat::rtio_error_write(2);
                }
                drtioaux::send_link(0,
                    &drtioaux::Packet::RtioErrorCollisionReply { channel })
            } else if errors & 4 != 0 {
                let channel;
                unsafe {
                    channel = csr::drtiosat::busy_channel_read();
                    csr::drtiosat::rtio_error_write(4);
                }
                drtioaux::send_link(0,
                    &drtioaux::Packet::RtioErrorBusyReply { channel })
            }
            else {
                drtioaux::send_link(0, &drtioaux::Packet::RtioNoErrorReply)
            }
        }

        #[cfg(has_drtio_routing)]
        drtioaux::Packet::RoutingSetPath { destination, hops } => {
            _routing_table.0[destination as usize] = hops;
            for rep in _repeaters.iter() {
                if let Err(e) = rep.set_path(destination, &hops) {
                    error!("failed to set path ({})", e);
                }
            }
            drtioaux::send_link(0, &drtioaux::Packet::RoutingAck)
        }
        #[cfg(has_drtio_routing)]
        drtioaux::Packet::RoutingSetRank { rank } => {
            *_rank = rank;
            drtio_routing::program_interconnect(_routing_table, rank);

            let rep_rank = rank + 1;
            for rep in _repeaters.iter() {
                if let Err(e) = rep.set_rank(rep_rank) {
                    error!("failed to set rank ({})", e);
                }
            }

            info!("rank: {}", rank);
            info!("routing table: {}", _routing_table);

            drtioaux::send_link(0, &drtioaux::Packet::RoutingAck)
        }

        #[cfg(not(has_drtio_routing))]
        drtioaux::Packet::RoutingSetPath { _destination, _hops } => {
            drtioaux::send_link(0, &drtioaux::Packet::RoutingAck)
        }
        #[cfg(not(has_drtio_routing))]
        drtioaux::Packet::RoutingSetRank { _rank } => {
            drtioaux::send_link(0, &drtioaux::Packet::RoutingAck)
        }

        drtioaux::Packet::MonitorRequest { channel, probe } => {
            let value;
            #[cfg(has_rtio_moninj)]
            unsafe {
                csr::rtio_moninj::mon_chan_sel_write(channel as _);
                csr::rtio_moninj::mon_probe_sel_write(probe);
                csr::rtio_moninj::mon_value_update_write(1);
                value = csr::rtio_moninj::mon_value_read();
            }
            #[cfg(not(has_rtio_moninj))]
            {
                value = 0;
            }
            let reply = drtioaux::Packet::MonitorReply { value: value as u32 };
            drtioaux::send_link(0, &reply)
        },
        drtioaux::Packet::InjectionRequest { channel, overrd, value } => {
            #[cfg(has_rtio_moninj)]
            unsafe {
                csr::rtio_moninj::inj_chan_sel_write(channel as _);
                csr::rtio_moninj::inj_override_sel_write(overrd);
                csr::rtio_moninj::inj_value_write(value);
            }
            Ok(())
        },
        drtioaux::Packet::InjectionStatusRequest { channel, overrd } => {
            let value;
            #[cfg(has_rtio_moninj)]
            unsafe {
                csr::rtio_moninj::inj_chan_sel_write(channel as _);
                csr::rtio_moninj::inj_override_sel_write(overrd);
                value = csr::rtio_moninj::inj_value_read();
            }
            #[cfg(not(has_rtio_moninj))]
            {
                value = 0;
            }
            drtioaux::send_link(0, &drtioaux::Packet::InjectionStatusReply { value: value })
        },

        drtioaux::Packet::I2cStartRequest { busno } => {
            let succeeded = i2c::start(busno).is_ok();
            drtioaux::send_link(0, &drtioaux::Packet::I2cBasicReply { succeeded: succeeded })
        }
        drtioaux::Packet::I2cRestartRequest { busno } => {
            let succeeded = i2c::restart(busno).is_ok();
            drtioaux::send_link(0, &drtioaux::Packet::I2cBasicReply { succeeded: succeeded })
        }
        drtioaux::Packet::I2cStopRequest { busno } => {
            let succeeded = i2c::stop(busno).is_ok();
            drtioaux::send_link(0, &drtioaux::Packet::I2cBasicReply { succeeded: succeeded })
        }
        drtioaux::Packet::I2cWriteRequest { busno, data } => {
            match i2c::write(busno, data) {
                Ok(ack) => drtioaux::send_link(0,
                    &drtioaux::Packet::I2cWriteReply { succeeded: true, ack: ack }),
                Err(_) => drtioaux::send_link(0,
                    &drtioaux::Packet::I2cWriteReply { succeeded: false, ack: false })
            }
        }
        drtioaux::Packet::I2cReadRequest { busno, ack } => {
            match i2c::read(busno, ack) {
                Ok(data) => drtioaux::send_link(0,
                    &drtioaux::Packet::I2cReadReply { succeeded: true, data: data }),
                Err(_) => drtioaux::send_link(0,
                    &drtioaux::Packet::I2cReadReply { succeeded: false, data: 0xff })
            }
        }

        drtioaux::Packet::SpiSetConfigRequest { busno, flags, length, div, cs } => {
            let succeeded = spi::set_config(busno, flags, length, div, cs).is_ok();
            drtioaux::send_link(0,
                &drtioaux::Packet::SpiBasicReply { succeeded: succeeded })
        },
        drtioaux::Packet::SpiWriteRequest { busno, data } => {
            let succeeded = spi::write(busno, data).is_ok();
            drtioaux::send_link(0,
                &drtioaux::Packet::SpiBasicReply { succeeded: succeeded })
        }
        drtioaux::Packet::SpiReadRequest { busno } => {
            match spi::read(busno) {
                Ok(data) => drtioaux::send_link(0,
                    &drtioaux::Packet::SpiReadReply { succeeded: true, data: data }),
                Err(_) => drtioaux::send_link(0,
                    &drtioaux::Packet::SpiReadReply { succeeded: false, data: 0 })
            }
        }

        _ => {
            warn!("received unexpected aux packet");
            Ok(())
        }
    }
}

fn process_aux_packets(repeaters: &mut [repeater::Repeater],
        routing_table: &mut drtio_routing::RoutingTable, rank: &mut u8) {
    let result =
        drtioaux::recv_link(0).and_then(|packet| {
            if let Some(packet) = packet {
                process_aux_packet(repeaters, routing_table, rank, packet)
            } else {
                Ok(())
            }
        });
    match result {
        Ok(()) => (),
        Err(e) => warn!("aux packet error ({})", e)
    }
}

fn drtiosat_process_errors() {
    let errors;
    unsafe {
        errors = csr::drtiosat::protocol_error_read();
    }
    if errors & 1 != 0 {
        error!("received packet of an unknown type");
    }
    if errors & 2 != 0 {
        error!("received truncated packet");
    }
    if errors & 4 != 0 {
        let destination;
        unsafe {
            destination = csr::drtiosat::buffer_space_timeout_dest_read();
        }
        error!("timeout attempting to get buffer space from CRI, destination=0x{:02x}", destination)
    }
    if errors & 8 != 0 {
        let channel;
        let timestamp_event;
        let timestamp_counter;
        unsafe {
            channel = csr::drtiosat::underflow_channel_read();
            timestamp_event = csr::drtiosat::underflow_timestamp_event_read() as i64;
            timestamp_counter = csr::drtiosat::underflow_timestamp_counter_read() as i64;
        }
        error!("write underflow, channel={}, timestamp={}, counter={}, slack={}",
               channel, timestamp_event, timestamp_counter, timestamp_event-timestamp_counter);
    }
    if errors & 16 != 0 {
        error!("write overflow");
    }
    unsafe {
        csr::drtiosat::protocol_error_write(errors);
    }
}

#[cfg(rtio_frequency = "150.0")]
const SI5324_SETTINGS: si5324::FrequencySettings
    = si5324::FrequencySettings {
    n1_hs  : 6,
    nc1_ls : 6,
    n2_hs  : 10,
    n2_ls  : 270,
    n31    : 75,
    n32    : 75,
    bwsel  : 4,
    crystal_ref: true
};

const SIPHASER_PHASE: u16 = 32;

#[no_mangle]
pub extern fn main() -> i32 {
    clock::init();
    uart_logger::ConsoleLogger::register();

    info!("ARTIQ satellite manager starting...");
    info!("software ident {}", csr::CONFIG_IDENTIFIER_STR);
    info!("gateware ident {}", ident::read(&mut [0; 64]));

    #[cfg(has_slave_fpga_cfg)]
    board_artiq::slave_fpga::load().expect("cannot load RTM FPGA gateware");
    #[cfg(has_serwb_phy_amc)]
    serwb::wait_init();

    i2c::init();
    si5324::setup(&SI5324_SETTINGS, si5324::Input::Ckin1).expect("cannot initialize Si5324");
    #[cfg(has_hmc830_7043)]
    /* must be the first SPI init because of HMC830 SPI mode selection */
    hmc830_7043::init().expect("cannot initialize HMC830/7043");
    unsafe {
        csr::drtio_transceiver::stable_clkin_write(1);
    }

    #[cfg(has_allaki_atts)]
    board_artiq::hmc542::program_all(8/*=4dB*/);

    #[cfg(has_drtio_routing)]
    let mut repeaters = [repeater::Repeater::default(); csr::DRTIOREP.len()];
    #[cfg(not(has_drtio_routing))]
    let mut repeaters = [repeater::Repeater::default(); 0];
    for i in 0..repeaters.len() {
        repeaters[i] = repeater::Repeater::new(i as u8);
    } 
    let mut routing_table = drtio_routing::RoutingTable::default_empty();
    let mut rank = 1;

    loop {
        while !drtiosat_link_rx_up() {
            drtiosat_process_errors();
            for mut rep in repeaters.iter_mut() {
                rep.service(&routing_table, rank);
            }
        }

        info!("uplink is up, switching to recovered clock");
        si5324::siphaser::select_recovered_clock(true).expect("failed to switch clocks");
        si5324::siphaser::calibrate_skew(SIPHASER_PHASE).expect("failed to calibrate skew");

        #[cfg(has_ad9154)]
        {
            /*
             * One side of the JESD204 elastic buffer is clocked by the Si5324, the other
             * by the RTM.
             * The elastic buffer can operate only when those two clocks are derived from
             * the same oscillator.
             * This is the case when either of those conditions is true:
             * (1) The DRTIO master and the RTM are clocked directly from a common external
             *     source, *and* the Si5324 has locked to the recovered clock.
             *     This clocking scheme provides less noise and phase drift at the DACs.
             * (2) The RTM clock is connected to the Si5324 output.
             * To handle those cases, we simply keep the JESD204 core in reset unless the
             * Si5324 is locked to the recovered clock.
             */
            board_artiq::ad9154::jesd_reset(false);
            board_artiq::ad9154::init();
        }

        drtioaux::reset(0);
        drtiosat_reset(false);
        drtiosat_reset_phy(false);

        while drtiosat_link_rx_up() {
            drtiosat_process_errors();
            process_aux_packets(&mut repeaters, &mut routing_table, &mut rank);
            for mut rep in repeaters.iter_mut() {
                rep.service(&routing_table, rank);
            }
            if drtiosat_tsc_loaded() {
                info!("TSC loaded from uplink");
                #[cfg(has_ad9154)]
                {
                    if let Err(e) = board_artiq::jesd204sync::sysref_auto_rtio_align() {
                        error!("failed to align SYSREF at FPGA: {}", e);
                    }
                    if let Err(e) = board_artiq::jesd204sync::sysref_auto_dac_align() {
                        error!("failed to align SYSREF at DAC: {}", e);
                    }
                }
                for rep in repeaters.iter() {
                    if let Err(e) = rep.sync_tsc() {
                        error!("failed to sync TSC ({})", e);
                    }
                }
                if let Err(e) = drtioaux::send_link(0, &drtioaux::Packet::TSCAck) {
                    error!("aux packet error: {}", e);
                }
            }
        }

        #[cfg(has_ad9154)]
        board_artiq::ad9154::jesd_reset(true);

        drtiosat_reset_phy(true);
        drtiosat_reset(true);
        drtiosat_tsc_loaded();
        info!("uplink is down, switching to local crystal clock");
        si5324::siphaser::select_recovered_clock(false).expect("failed to switch clocks");
    }
}

#[no_mangle]
pub extern fn exception(vect: u32, _regs: *const u32, pc: u32, ea: u32) {
    let vect = irq::Exception::try_from(vect).expect("unknown exception");

    fn hexdump(addr: u32) {
        let addr = (addr - addr % 4) as *const u32;
        let mut ptr  = addr;
        println!("@ {:08p}", ptr);
        for _ in 0..4 {
            print!("+{:04x}: ", ptr as usize - addr as usize);
            print!("{:08x} ",   unsafe { *ptr }); ptr = ptr.wrapping_offset(1);
            print!("{:08x} ",   unsafe { *ptr }); ptr = ptr.wrapping_offset(1);
            print!("{:08x} ",   unsafe { *ptr }); ptr = ptr.wrapping_offset(1);
            print!("{:08x}\n",  unsafe { *ptr }); ptr = ptr.wrapping_offset(1);
        }
    }

    hexdump(pc);
    hexdump(ea);
    panic!("exception {:?} at PC 0x{:x}, EA 0x{:x}", vect, pc, ea)
}

#[no_mangle]
pub extern fn abort() {
    println!("aborted");
    loop {}
}

#[no_mangle] // https://github.com/rust-lang/rust/issues/{38281,51647}
#[panic_implementation]
pub fn panic_fmt(info: &core::panic::PanicInfo) -> ! {
    if let Some(location) = info.location() {
        print!("panic at {}:{}:{}", location.file(), location.line(), location.column());
    } else {
        print!("panic at unknown location");
    }
    if let Some(message) = info.message() {
        println!(": {}", message);
    } else {
        println!("");
    }
    loop {}
}
