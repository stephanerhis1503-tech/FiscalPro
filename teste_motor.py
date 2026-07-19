from src.services.motor_fiscal import MotorFiscal

motor = MotorFiscal()

print(motor.validar_ncm("87141000"))

print(motor.validar_ncm("99999999"))

print(motor.validar_cfop("2102"))

print(motor.validar_cfop(""))