package risk.enforcement.policy.verify.policy_0353

# Auto-generated policy 353 (Rego v1 syntax)
# Package: risk.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0353",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0353_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0353_allowed if {
    input.user.role == "admin"
}
policy_0353_allowed if {
    input.user.active
    input.resource.public
}
