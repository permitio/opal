package governance.authorization.policy.deny.policy_0602

# Auto-generated policy 602 (Rego v1 syntax)
# Package: governance.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0602",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0602_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0602_allowed if {
    input.user.role == "admin"
}
default policy_0602_allowed = false
