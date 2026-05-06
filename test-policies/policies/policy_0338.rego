package compliance.enforcement.policy.allow.policy_0338

# Auto-generated policy 338 (Rego v1 syntax)
# Package: compliance.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0338",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0338_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0338_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0338_allowed if {
    input.user.role == "admin"
}
policy_0338_allowed if {
    input.user.active
    input.resource.public
}
