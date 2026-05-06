package governance.enforcement.user.verify.policy_0815

# Auto-generated policy 815 (Rego v1 syntax)
# Package: governance.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0815",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0815_allowed if {
    input.user.active
    input.resource.public
}
policy_0815_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0815_allowed if {
    data.policies.governance.enabled
}
