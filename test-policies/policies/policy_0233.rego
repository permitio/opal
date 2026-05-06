package security.enforcement.action.check.policy_0233

# Auto-generated policy 233 (Rego v1 syntax)
# Package: security.enforcement.action.check

# Metadata
metadata := {
    "policy_id": "0233",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0233_allowed if {
    input.user.role == "admin"
}
policy_0233_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
