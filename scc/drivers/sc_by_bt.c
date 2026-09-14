#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <inttypes.h>
#include <stdbool.h>
#include <limits.h>
#include <stdio.h>

#define SC_BY_BT_MODULE_VERSION 3

enum BtInPacketType {
	BUTTON   = 0x0010,
	TRIGGERS = 0x0020,
	LSTICK   = 0x0080,
	LPAD     = 0x0100,
	RPAD     = 0x0200,
	GYRO     = 0x1800,
	PING     = 0x5000,
};

#define LONG_PACKET 0x80
#define SINGLE_PACKET_PAYLOAD_PREFIX 0x40
#define PACKET_SIZE 20

enum SCButtons {
	// This may be moved later to something shared, only this c file needs it right now
	SCB_RPADTOUCH   = 0b0010000000000000000000000000000,
	SCB_LPADTOUCH   = 0b0001000000000000000000000000000,
	SCB_RPADPRESS   = 0b0000100000000000000000000000000,
	SCB_LPADPRESS   = 0b0000010000000000000000000000000, // Same for stick but without LPadTouch
	SCB_LSTICKPRESS = 0b1000000000000000000000000000000, // Generated internally, not sent by controller
	SCB_RGRIP       = 0b0000001000000000000000000000000,
	SCB_LGRIP       = 0b0000000100000000000000000000000,
	SCB_START       = 0b0000000010000000000000000000000,
	SCB_C           = 0b0000000001000000000000000000000,
	SCB_BACK        = 0b0000000000100000000000000000000,
	SCB_A           = 0b0000000000000001000000000000000,
	SCB_X           = 0b0000000000000000100000000000000,
	SCB_B           = 0b0000000000000000010000000000000,
	SCB_Y           = 0b0000000000000000001000000000000,
	SCB_LB          = 0b0000000000000000000100000000000,
	SCB_RB          = 0b0000000000000000000010000000000,
	SCB_LT          = 0b0000000000000000000001000000000,
	SCB_RT          = 0b0000000000000000000000100000000,
	SCB_CPADTOUCH   = 0b0000000000000000000000000000100, // Available on DS4/DualSense
	SCB_CPADPRESS   = 0b0000000000000000000000000000010, // Available on DS4/DualSense
};

struct SCByBtControllerInput {
	uint16_t type;
	uint32_t buttons;
	uint8_t ltrig;
	uint8_t rtrig;
	int32_t lstick_x;
	int32_t lstick_y;
	int32_t lpad_x;
	int32_t lpad_y;
	int32_t rpad_x;
	int32_t rpad_y;
	int32_t accel_x;
	int32_t accel_y;
	int32_t accel_z;
	int32_t gpitch;
	int32_t groll;
	int32_t gyaw;
	int32_t q1;
	int32_t q2;
	int32_t q3;
	int32_t q4;
};

struct SCByBtC {
	int fileno;
	char buffer[256];
	uint8_t long_packet; // Next expected fragment number; zero means idle.
	struct SCByBtControllerInput state;
	struct SCByBtControllerInput old_state;
};

typedef struct SCByBtC* SCByBtCPtr;

#define BT_BUTTONS_BITS 23

static uint32_t BT_BUTTONS[] = {
	// Bit to SCButton
	SCB_RT,					// 00
	SCB_LT,					// 01
	SCB_RB,					// 02
	SCB_LB,					// 03
	SCB_Y,					// 04
	SCB_B,					// 05
	SCB_X,					// 06
	SCB_A,					// 07
	0, 						// 08 - dpad, ignored
	0, 						// 09 - dpad, ignored
	0, 						// 10 - dpad, ignored
	0, 						// 11 - dpad, ignored
	SCB_BACK,				// 12
	SCB_C,					// 13
	SCB_START,				// 14
	SCB_LGRIP,				// 15
	SCB_RGRIP,				// 16
	SCB_LPADPRESS,				// 17
	SCB_RPADPRESS,				// 18
	SCB_LPADTOUCH,			// 19
	SCB_RPADTOUCH,			// 20
	0,						// 21 - nothing
	SCB_LSTICKPRESS,			// 22
};

static inline void debug_packet(char* buffer, size_t size) {
	size_t i;
	for(i=0; i<size; i++)
		printf("%02x ", buffer[i] & 0xff);
	printf("\n");
}

static char tmp_buffer[256];

/** Returns 1 if state has changed, 2 on read error */
int read_input(SCByBtCPtr ptr) {
	if (read(ptr->fileno, tmp_buffer, PACKET_SIZE) < PACKET_SIZE)
	{
		return 2;
	}

	uint8_t header = (uint8_t)tmp_buffer[1];
	unsigned int packet = header & 0x0f;
	bool complete = (header & SINGLE_PACKET_PAYLOAD_PREFIX) != 0;
	size_t offset = 2 + (PACKET_SIZE - 2) * (size_t)packet;

	if ((uint8_t)tmp_buffer[0] != 3) {
		fprintf(stderr, "SCBT: rejected unexpected report ID: fd=%d id=0x%02x\n",
			ptr->fileno, (unsigned int)(uint8_t)tmp_buffer[0]);
		ptr->long_packet = 0;
		memset(ptr->buffer, 0, sizeof(ptr->buffer));
		return 0;
	}
	if (packet == 0) {
		// A new message resynchronizes after a lost final fragment.
		if (ptr->long_packet)
			fprintf(stderr, "SCBT: discarded incomplete message: fd=%d expected=%u got=0\n",
				ptr->fileno, (unsigned int)ptr->long_packet);
		ptr->long_packet = 0;
		memset(ptr->buffer, 0, sizeof(ptr->buffer));
	} else if (!ptr->long_packet || packet != ptr->long_packet) {
		fprintf(stderr, "SCBT: rejected out-of-sequence fragment: fd=%d expected=%u got=%u\n",
			ptr->fileno, (unsigned int)ptr->long_packet, packet);
		ptr->long_packet = 0;
		memset(ptr->buffer, 0, sizeof(ptr->buffer));
		return 0;
	}
	if (offset + (PACKET_SIZE - 2) > sizeof(ptr->buffer)) {
		fprintf(stderr,
			"SCBT: rejected packet buffer overflow: fd=%d packet=%u header=0x%02x "
			"offset=%zu copy_size=%zu buffer_size=%zu\n",
			ptr->fileno, packet, (unsigned int)header,
			offset, (size_t)(PACKET_SIZE - 2), sizeof(ptr->buffer));
		ptr->long_packet = 0;
		memset(ptr->buffer, 0, sizeof(ptr->buffer));
		return 0;
	}
	memcpy(ptr->buffer + offset, tmp_buffer + 2, PACKET_SIZE - 2);
	ptr->long_packet = complete ? 0 : packet + 1;
	if (!complete)
		return 0;

	// Do not decode fields that were never received, even if the buffer fits.
	size_t received = offset + (PACKET_SIZE - 2) - 4;
	uint16_t type = (uint8_t)ptr->buffer[2] | ((uint16_t)(uint8_t)ptr->buffer[3] << 8);
	if ((type & PING) == PING)
		return 0;
	size_t required = 0;
	if (type & BUTTON) required += 3;
	if (type & TRIGGERS) required += 2;
	if (type & LSTICK) required += 4;
	if (type & LPAD) required += 4;
	if (type & RPAD) required += 4;
	if ((type & GYRO) == GYRO) required += 20;
	if (required > received) {
		fprintf(stderr, "SCBT: rejected truncated message: fd=%d type=0x%04x required=%zu received=%zu\n",
			ptr->fileno, (unsigned int)type, required, received);
		memset(ptr->buffer, 0, sizeof(ptr->buffer));
		return 0;
	}

	struct SCByBtControllerInput* state = &(ptr->state);
	struct SCByBtControllerInput* old_state = &(ptr->old_state);

	int rv = 0;
	int bit;
	char* data = &ptr->buffer[4];
	if ((type & BUTTON) == BUTTON) {
		uint32_t bt_buttons = (uint8_t)data[0] | ((uint32_t)(uint8_t)data[1] << 8)
			| ((uint32_t)(uint8_t)data[2] << 16);
		uint32_t sc_buttons = 0;
		for (bit=0; bit<BT_BUTTONS_BITS; bit++) {
			if ((bt_buttons & 1) != 0)
				sc_buttons |= BT_BUTTONS[bit];
			bt_buttons >>= 1;
		}

		if (rv == 0) { *old_state = *state; state->type = type; rv = 1; }
		state->buttons = sc_buttons;
		data += 3;
	}
	if ((type & TRIGGERS) == TRIGGERS) {
		if (rv == 0) { *old_state = *state; state->type = type; rv = 1; }
		state->ltrig = *(((uint8_t*)data) + 0);
		state->rtrig = *(((uint8_t*)data) + 1);
		data += 2;
	}
	if ((type & LSTICK) == LSTICK) {
		if (rv == 0) { *old_state = *state; state->type = type; rv = 1; }
		state->lstick_x = *(((int16_t*)data) + 0);
		state->lstick_y = *(((int16_t*)data) + 1);
		data += 4;
	}
	if ((type & LPAD) == LPAD) {
		if (rv == 0) { *old_state = *state; state->type = type; rv = 1; }
		state->lpad_x = *(((int16_t*)data) + 0);
		state->lpad_y = *(((int16_t*)data) + 1);
		data += 4;
	}
	if ((type & RPAD) == RPAD) {
		if (rv == 0) { *old_state = *state; state->type = type; rv = 1; }
		state->rpad_x = *(((int16_t*)data) + 0);
		state->rpad_y = *(((int16_t*)data) + 1);
		data += 4;
	}
	if ((type & GYRO) == GYRO) {
		if (rv == 0) { *old_state = *state; state->type = type; rv = 1; }
		state->accel_x = *(((int16_t*)data) + 0);
		state->accel_y = *(((int16_t*)data) + 1);
		state->accel_z = *(((int16_t*)data) + 2);
		state->gpitch = *(((int16_t*)data) + 3);
		state->groll = *(((int16_t*)data) + 4);
		state->gyaw = *(((int16_t*)data) + 5);
		state->q1 = *(((int16_t*)data) + 6);
		state->q2 = *(((int16_t*)data) + 7);
		state->q3 = *(((int16_t*)data) + 8);
		state->q4 = *(((int16_t*)data) + 9);
		data += 20;
		/*state->gpitch = *(((int16_t*)data) + 0);
		state->groll = *(((int16_t*)data) + 1);
		state->gyaw = *(((int16_t*)data) + 2);
		state->q1 = *(((int16_t*)data) + 3);
		state->q2 = *(((int16_t*)data) + 4);
		state->q3 = *(((int16_t*)data) + 5);
		state->q4 = *(((int16_t*)data) + 6);
		data += 14;
		*/
	}


	return rv;
}

const int sc_by_bt_module_version(void) {
	return SC_BY_BT_MODULE_VERSION;
}
