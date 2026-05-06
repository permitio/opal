package governance.enforcement.user.check.policy_0474

# Auto-generated policy 474 (Rego v1 syntax)
# Package: governance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0474",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0474_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0474_allowed if {
    data.policies.governance.enabled
}
policy_0474_allowed if {
    input.user.role == "admin"
}
