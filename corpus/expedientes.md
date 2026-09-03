# Expediente digital de proveedores

Un expediente reúne los documentos que acreditan a un proveedor antes de
habilitarlo para operar.

## Documentos que lo integran

Constancia de Situación Fiscal, identificación oficial del representante,
comprobante de domicilio, acta constitutiva cuando es persona moral, poder
notarial cuando quien firma no es el representante legal, y carátula bancaria
para el pago.

## Vigencias

El comprobante de domicilio y la opinión de cumplimiento tienen vigencia
limitada. Un expediente aprobado con documentos vencidos deja de ser válido
aunque nadie lo haya marcado como tal, por lo que la vigencia se revisa en
cada operación y no solo al momento del alta.

## Validación automática

La validación compara el RFC declarado contra el que aparece en la Constancia
de Situación Fiscal. Cuando el archivo es un escaneo sin capa de texto, se
extrae el contenido por reconocimiento óptico de caracteres antes de comparar.

Un documento que no puede leerse se rechaza en la carga y no en la revisión
manual posterior, para que el proveedor lo corrija de inmediato.
