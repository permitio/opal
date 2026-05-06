package governance.enforcement.policy.verify.policy_0411

# Auto-generated policy 411 (Rego v1 syntax)
# Package: governance.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0411",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0411_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0411_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0411_allowed if {
    input.user.role == "admin"
}
policy_0411_allowed if {
    data.policies.governance.enabled
}
