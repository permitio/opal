package compliance.enforcement.user.deny.policy_0989

# Auto-generated policy 989 (Rego v1 syntax)
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0989",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0989_allowed if {
    data.policies.compliance.enabled
}
policy_0989_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
