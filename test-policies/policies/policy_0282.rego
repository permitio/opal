package audit.authentication.resource.check.policy_0282

# Auto-generated policy 282 (Rego v1 syntax)
# Package: audit.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0282",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0282_allowed if {
    input.user.active
    input.resource.public
}
policy_0282_allowed if {
    data.policies.audit.enabled
}
