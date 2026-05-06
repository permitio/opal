package risk.enforcement.action.verify.data.policy_0155

# Auto-generated policy 155 (Rego v1 syntax)
# Package: risk.enforcement.action.verify.data

# Metadata
metadata := {
    "policy_id": "0155",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0155_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0155_allowed if {
    input.user.role == "admin"
}
