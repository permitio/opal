package security.authentication.policy.check.data.policy_0260

# Auto-generated policy 260 (Rego v1 syntax)
# Package: security.authentication.policy.check.data

# Metadata
metadata := {
    "policy_id": "0260",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0260_allowed if {
    input.user.role == "admin"
}
policy_0260_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
